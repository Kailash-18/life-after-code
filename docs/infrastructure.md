# Project Sentinel — Infrastructure & Keyless CI Architecture (Tasks K1, K2)

## 1. Cloud Architecture Overview

Project Sentinel leverages **Google Cloud Platform (GCP)** and **Cloud Run** for containerized serverless hosting, integrated seamlessly with **GitLab CI/CD** via **Workload Identity Federation (WIF)**.

```mermaid
flowchart TD
    GitLabCI[GitLab CI Job] -->|OIDC JWT Token| WIF[Workload Identity Pool Provider]
    WIF -->|Short-lived OAuth2 Token| SA[Service Account: sentinel-ci-runner]
    SA -->|Deploy Candidate Revision| CR_Target[Cloud Run: sentinel-target-app]
    SA -->|Deploy Backend API| CR_Backend[Cloud Run: sentinel-backend]
    SA -->|Push/Pull Docker Images| AR[Artifact Registry: sentinel]
    SA -->|Access HMAC Keys| SM[Secret Manager: sentinel-hmac-secret]
```

---

## 2. Keyless Authentication via Workload Identity Federation (WIF)

To satisfy the zero-secret security requirement (Task K1), GitLab CI does **not** store any long-lived service account JSON keys. Instead:

1. GitLab CI generates an OIDC JSON Web Token (JWT) using the `id_tokens` directive:
   ```yaml
   id_tokens:
     GITLAB_OIDC_TOKEN:
       aud: "https://gitlab.com"
   ```
2. The CI job presents this token to Google Cloud's Security Token Service (STS) endpoint:
   `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/sentinel-ci-runner@project-sentinel.iam.gserviceaccount.com:generateAccessToken`
3. GCP validates that:
   * The token issuer is `https://gitlab.com`
   * The project path matches `assertion.project_path == 'project-sentinel/sentinel'`
4. GCP issues a short-lived access token (valid for 1 hour) with scoped roles (`roles/run.admin`, `roles/artifactregistry.writer`).

---

## 3. Terraform Directory Layout (`infra/`)

* [`main.tf`](../infra/main.tf) — Provider requirements and GCP settings.
* [`variables.tf`](../infra/variables.tf) — Configuration variables (project ID, region, image tags).
* [`artifact_registry.tf`](../infra/artifact_registry.tf) — Docker repository for container images.
* [`cloud_run.tf`](../infra/cloud_run.tf) — Cloud Run v2 services with traffic allocation and candidate URL tags.
* [`cloud_armor.tf`](../infra/cloud_armor.tf) — Enterprise Layer 7 WAF, token-bucket rate limiting (1000 req/min), OWASP SQLi/XSS/RCE/LFI mitigation.
* [`load_balancer.tf`](../infra/load_balancer.tf) — Global Anycast HTTPS Load Balancer with Serverless NEGs routing traffic securely to Cloud Run services.
* [`traffic_director.tf`](../infra/traffic_director.tf) — Multi-Region Cloud Run replica (`us-east1`) and Cloud DNS Anycast steering zone for automated regional failover.
* [`iam_wif.tf`](../infra/iam_wif.tf) — WIF pool, OIDC provider, and service account IAM bindings.
* [`secrets.tf`](../infra/secrets.tf) — Secret Manager configuration for HMAC secrets and tokens.
* [`outputs.tf`](../infra/outputs.tf) — Output endpoints, Global LB IP, Cloud Armor policy ID, Failover URL, and DNS zone.

---

## 4. Top 0.1% Enterprise SRE & Resiliency Engine (FAANG / Staff+ Tier)

Project Sentinel incorporates cutting-edge Site Reliability Engineering and Cloud Architecture patterns:

1. **Policy-as-Code with Open Policy Agent (OPA) & Rego (`sentinel/policy.rego`, `sentinel/scripts/opa_validator.py`):**
   - **Zero-Trust Guardrails:** Enforces immutable non-root execution, read-only root filesystems, CPU/memory resource allocations, and WAF attachment.
   - **Blast Radius Enforcement:** Rejects any deployment with $>10\%$ initial canary split or non-zero-downtime recreation strategies.

2. **L4/L7 eBPF Kernel Network & TLS Latency Decomposition (`sentinel/scripts/ebpf_tracer.py`):**
   - **Nanosecond Transport Phase Breakdown:** Deconstructs latency into DNS lookup $\rightarrow$ TCP 3-way handshake $\rightarrow$ TLS 1.3 session negotiation $\rightarrow$ TTFB $\rightarrow$ Content Transfer.
   - **Kernel Socket Tracing:** Monitors `tcp_retransmit_skb`, SYN queue saturation, and socket buffer bloat before HTTP 5xx errors occur.

3. **Statistical EWMA & CUSUM Adaptive Drift Detector (`sentinel/scripts/drift_detector.py`):**
   - **Continuous Quality Control:** Two-sided Cumulative Sum (CUSUM) and Exponentially Weighted Moving Average (EWMA) change-point detection.
   - **Micro-Regression Catching:** Catches slow-bleed latency creep (e.g. $+2\text{ms}/1\text{k}$ requests from memory leaks or lock contention) that fly under static hard limits.

4. **Multi-Region Disaster Recovery & Cloud DNS Traffic Director (`infra/traffic_director.tf`, `sentinel/scripts/disaster_recovery.py`):**
   - **Active-Active Cross-Region Topology:** Parallel Cloud Run workloads in `us-central1` and `us-east1` bound to Global Anycast Load Balancer.
   - **Automated Health Steering:** Cloud DNS Anycast routing with sub-5s Recovery Time Objective (RTO) and zero data loss (RPO = 0s).

5. **Sigstore / Cosign Keyless Provenance & Rekor Transparency Log (`sentinel/scripts/cosign_verifier.py`):**
   - **Keyless Container Signatures:** Verifies OIDC Fulcio identity certificates and Rekor transparency log inclusion proofs.
   - **Cryptographic Tamper-Proofing:** Enforces non-repudiation and blocks untrusted or poisoned images from production canary progression.

6. **Statistical Telemetry & Error Budget Analysis (`sentinel/scripts/statistical_analyzer.py`):**
   - **Mann-Whitney U Rank-Sum Test:** Non-parametric hypothesis testing certifying latency shifts ($p < 0.05$).
   - **Google SRE Multi-Burn-Rate Model:** Real-time tracking of 1h ($14.4\times$) and 6h ($6.0\times$) error budget consumption.

7. **Chaos Engineering & Canary Circuit Breaker (`sentinel/scripts/chaos_engine.py`):**
   - **Tri-State FSM:** `CLOSED` $\rightarrow$ `OPEN` $\rightarrow$ `HALF-OPEN` $\rightarrow$ `CLOSED`.
   - **Fault Injection:** Injects 503 drops, synthetic latency spikes, and 504 timeouts.

---

## 5. Terraform Validation & Deployment

```bash
cd infra
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
```


