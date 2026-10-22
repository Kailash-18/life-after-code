# Project Sentinel — 9-Stage DevSecOps Lifecycle Architecture

> **Devpost GitLab Transcend Hackathon Submission**  
> **Prize Target:** Most Stages Covered ($5,000) & Hands-Off Autonomy ($5,000)  
> **Google Cloud Bonus:** 0.2 Bonus Points (Cloud Run, Cloud Armor, KMS, Cloud Monitoring)  
> **Autonomy Level:** **Hands-Off** (AI proposes repairs; deterministic gates decide; CI executes actions)

---

## 1. Executive Summary

Project Sentinel takes over the entire post-code DevSecOps lifecycle through autonomous, evidence-backed closed-loop agents and deterministic verification gates. Rather than relying on human engineers to manually detect alerts, triage stacktraces, patch code, and push hotfixes, Sentinel operates a complete, continuous **Hands-off loop**:

```
[Incubation / Incident Detection]
               │
               ▼
   [Stage 1: PLAN (FinOps & SCI Carbon Forecasting)]
               │
               ▼
   [Stage 2: CREATE (Automated Duo Repair MR & Schema Validation)]
               │
               ▼
   [Stage 3: VERIFY (Regression Proof & Kolmogorov-Smirnov Test)]
               │
               ▼
   [Stage 4: PACKAGE (CycloneDX SBOM, in-toto SLSA L3 & VEX Attestation)]
               │
               ▼
   [Stage 5: SECURE (Sentinel SAST, OPA Rego & Cloud Armor WAF)]
               │
               ▼
   [Stage 6: RELEASE (Tag-Isolated Canary & Sub-Second Rollback)]
               │
               ▼
   [Stage 7: CONFIGURE (Anycast Multi-Region Rebalancing & Cold-Start Priming)]
               │
               ▼
   [Stage 8: MONITOR (eBPF Kernel Socket Telemetry & Multi-Burn SLOs)]
               │
               ▼
   [Stage 9: GOVERN (CIS Multi-Cloud Zero-Trust & Immutable S3 State Sealing)]
```

---

## 2. DevSecOps 9-Stage Coverage Matrix

| Stage | GitLab Stage | Sentinel Autonomous Automation Engine | Output Artifact |
|---|---|---|---|
| **1** | `plan` | FinOps spend estimation (`finops_engine.py`) & ISO/IEC 21031 carbon intensity budget (`sci_carbon_engine.py`) | `artifacts/finops-spend-forecast.json`, `artifacts/sci-carbon-intensity.json` |
| **2** | `create` | Automated GitLab Duo AI repair MR generation & OpenAPI 3.1.0 contract validation | `artifacts/auto-repair-mr.json`, `docs/contracts/` |
| **3** | `verify` | Integrity Gate (test sanctity protection) & Non-Parametric Kolmogorov-Smirnov Latency Test (`ks_latency_comparator.py`) | `artifacts/integrity-gate-report.json`, `artifacts/ks-latency-report.json` |
| **4** | `package` | in-toto SLSA Level 3 provenance generator (`supply_chain_attestation.py`) & CycloneDX VEX Attestor (`vex_attestor.py`) | `artifacts/attestation-*.json`, `artifacts/cyclonedx-vex-report.json` |
| **5** | `secure` | Multi-directory AST SAST scanner (`sast_gate.py`), OPA Rego guardrails (`opa_validator.py`), Cloud Armor WAF mitigator (`cloud_armor_mitigator.py`) & KMS rotation auditor (`kms_rotation_auditor.py`) | `artifacts/sast-report.json`, `artifacts/opa-compliance-report.json`, `artifacts/kms-rotation-report.json` |
| **6** | `release` | Google Cloud Run private tag isolation (`candidate---tag`), blast-radius traffic stepping & sub-second instant rollback (`rollback.py`) | `artifacts/canary-deploy-report.json`, `artifacts/rollback-report.json` |
| **7** | `configure` | Anycast multi-region dynamic traffic rebalancer (`cloud_traffic_rebalancer.py`), Cloud Run concurrency tuner (`concurrency_autotuner.py`) & predictive cold-start primer daemon (`cold_start_primer.py`) | `artifacts/cloud-traffic-rebalance-report.json`, `artifacts/concurrency-tuning-report.json` |
| **8** | `monitor` | eBPF kernel network socket telemetry (`ebpf_tracer.py`), EWMA & CUSUM statistical drift detector (`drift_detector.py`) & Google Cloud SRE Multi-Window Multi-Burn SLO monitor (`cloud_sla_monitor.py`) | `artifacts/ebpf-telemetry-report.json`, `artifacts/sla-multi-burn-report.json` |
| **9** | `govern` | CIS Multi-Cloud Benchmark v2.0 auditor (`governance_guard.py`), S3 SSE-KMS remote state plane & cross-region zero-RPO replication (`s3_replication_auditor.py`) | `artifacts/governance-compliance-report.json`, `artifacts/s3-replication-report.json` |

---

## 3. Hands-Off Autonomy Architecture

Sentinel is engineered under the **Hands-off Autonomy Model**:
1. **Zero Human Intervention in Steady-State:**
   - When a regression or fault triggers in production, the monitoring layer flags an incident.
   - The Duo Agent flow analyzes the redacting evidence bundle, generates a targeted code fix, and opens a repair MR (`duo/fix/*`).
   - The authoritative CI pipeline executes the complete 9-stage verification battery.
   - If and only if all deterministic gates pass, Sentinel's autonomous merge engine executes the merge via project access token, tags the release, and canary-deploys to Cloud Run.
2. **Deterministic Quality Gates Override LLM Uncertainty:**
   - LLMs can hallucinate or weaken tests to make pipelines pass.
   - Sentinel's `integrity_gate.py` prevents any repair MR from deleting or loosening existing test assertions.
   - `regression_proof.py` verifies the test fails against the broken commit and passes against the candidate commit.

---

## 4. Google Cloud Production Deployment

All infrastructure and deployment code is version-controlled in [`infra/`](file:///c:/Users/Kailash/Downloads/Htz/LAC/life-after-code/infra/):
- **Cloud Run (Multi-Region Active-Active):** Primary region `us-central1`, secondary failover region `us-east1`.
- **Cloud Armor Edge WAF:** L7 DDoS rate limiting, SQLi/XSS signature inspection, and automatic IP threat mitigation.
- **Artifact Registry:** Docker container images signed with Sigstore Cosign keyless signatures.
- **Cloud KMS:** 90-day automatic key rotation with envelope encryption (DEK + KEK).
- **Cloud Monitoring & SRE:** 99.9% SLO multi-burn rate alerting windows (1h @ 14.4x, 6h @ 6.0x).

---

## 5. Verification Commands

To verify the full 9-stage DevSecOps lifecycle locally or in CI:

```bash
# 1. Execute unified 9-stage lifecycle orchestrator
python sentinel/scripts/lifecycle_orchestrator.py --output-dir artifacts

# 2. Run the turnkey 8-phase deployment engine
python scripts/deploy.py --dry-run

# 3. Run all unit and integration test suites
python -m pytest tests/
```
