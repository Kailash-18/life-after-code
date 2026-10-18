# Project Sentinel — Operations & Recovery Guide (Task K12)

This document is the authoritative operations manual for Project Sentinel's automated canary recovery loop, CI/CD pipeline, and Cloud Run infrastructure.

---

## 1. Architectural Philosophy

Project Sentinel implements an evidence-backed autonomous recovery loop grounded in three inviolable constraints:

1. **AI Proposes; Deterministic Gates Decide:** Duo flows may analyze incidents, synthesize root causes, and propose repair merge requests with regression tests, but they can **never** deploy to production, merge their own code, or declare recovery.
2. **Authoritative Sources Only:** No state upgrade is accepted without cryptographically signed proof from the authoritative component (e.g., only the Health Evaluator can declare health or recovery; only the Integrity Gate can certify test sanctity).
3. **No State Skipping:** Every recovery must traverse the linear state sequence:
   $$\text{DETECTED} \longrightarrow \text{ROLLED\_BACK} \longrightarrow \text{EVIDENCE\_COLLECTED} \longrightarrow \text{INVESTIGATING} \longrightarrow \text{REPAIR\_PROPOSED} \longrightarrow \text{VERIFYING} \longrightarrow \text{MERGED} \longrightarrow \text{REDEPLOYING} \longrightarrow \text{RECOVERED}$$

---

## 2. Pipeline Stages & Lifecycles

| Stage | Responsible Component | Authoritative Action | Emitted Event |
| :--- | :--- | :--- | :--- |
| `lint` | Ruff / Contract Validator | Validates OpenAPI 3.1.0 and JSON schemas | — |
| `test` | Pytest Runners | Executes Target App, Backend, and Gate test suites | — |
| `security` | `sentinel/scripts/sast_gate.py` | Scans for AST vulnerabilities, leaks, and eval/exec | `GateResult` |
| `infra` | Terraform | Validates Cloud Run, Artifact Registry, WIF definitions | — |
| `deploy-canary` | `sentinel/scripts/canary_deploy.py` | Deploys candidate with `--no-traffic --tag=candidate` | `deploy.canary_started` |
| `evaluate-canary`| `sentinel/scripts/evaluator.py` | Probes candidate vs stable baseline with synthetic load | `evaluator.verdict` |
| `rollback` | `sentinel/scripts/rollback.py` | Shifts 100% traffic back to known-good; runs health probe | `rollback.completed` |
| `evidence` | `sentinel/scripts/evidence_collector.py` | Redacts secrets; builds bundle; generates SHA-256 digest | `incident.detected`, `evidence.collected` |
| `gate-verify` | Regression Proof & Integrity Gate | Proves test fails on broken SHA and passes on fix SHA | `regression_proof.verdict`, `integrity_gate.verdict` |
| `auto-merge` | `sentinel/scripts/auto_merge.py` | Validates gate passes; merges repair MR via project token | `merge.completed` |
| `redeploy` | Cloud Run / Evaluator | Redeploys fixed revision; evaluates candidate at 100% traffic | `redeploy.completed`, `recovery.verified` |

---

## 3. Canary Rollout & Policy Configuration

The Health Evaluator enforces thresholds configured in [`sentinel/policy.yaml`](../sentinel/policy.yaml):

```yaml
thresholds:
  error_rate_max: 0.02              # Max 2% error rate permitted on candidate
  p95_latency_ms_max: 300.0         # Max 300ms p95 latency permitted
  health_endpoint_success_rate: 1.0 # 100% success required on /healthz
  max_error_rate_delta: 0.01        # Candidate error rate <= stable + 1.0%
  max_latency_ratio: 1.30           # Candidate p95 <= stable * 1.30
```

### Staged Rollout Steps
* **Stage 0 (0% traffic):** Deployed to private URL tag `https://candidate---sentinel-target-app-uc.a.run.app`. Tested with synthetic load before receiving any public traffic.
* **Stage 1 (10% traffic):** First public canary step. Evaluator runs 20+ probes across candidate and stable baseline.
* **Stage 2 (25% traffic):** Expanded canary.
* **Stage 3 (50% traffic):** Half traffic.
* **Stage 4 (100% traffic):** Full promotion.

---

## 4. Post-Incident Redeployment Strategies & Authoritative Recommendation

When a regression or defect is identified by the Health Evaluator, Sentinel formulates options for deploying the subsequent fix. The table below compares all deployment archetypes supported in [`sentinel/policy.yaml`](../sentinel/policy.yaml):

| Deployment Strategy | Blast Radius | Rollback Speed | Compute Overhead | Zero Downtime | State Corruption Risk | Suitability / Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **⭐ Progressive Canary (Tag-Isolated)** | **0% Tag / 10% Initial** | **< 1.5s (Cloud Run)** | **Low (Pay-per-use)** | **Yes** | **Very Low** | **Authoritative Recommendation (Best Choice)** |
| **Blue/Green Instant Cutover** | 100% upon switch | < 1.0s (Standby Revert) | High (+100% idle capacity) | Yes | Medium (Writes impact DB) | Viable for full-stack DB migrations |
| **Shadow / Traffic Mirroring** | 0% (Async Cloned) | N/A (No user impact) | Medium (2x ingress) | Yes | High for transactional mutations | Read-heavy APIs only |
| **Rolling Instance Replacement** | 20% - 33% | ~45-60s | Low | Yes | Medium | Legacy Kubernetes daemonsets |
| **Direct Recreate (In-Place)** | 100% | > 120s (Rebuild needed) | None | No (Downtime) | High | ❌ Prohibited for production recovery |

### Why Progressive Canary with Tag Isolation is the Best Choice:
1. **Zero-Traffic Pre-flight Testing:** Deploys the candidate under a private tag URL (`candidate`) with 0% public traffic. The Health Evaluator runs automated synthetic load probes (`/healthz`, `/metrics`, `/api/v1/orders`) before any live user ever touches the candidate revision.
2. **Strict Blast Radius Limitation:** When promoted to public traffic, it begins at just 10% allocation. If an edge-case failure occurs under live production traffic, at most 10% of users experience the issue, while 90% continue on the stable baseline.
3. **Sub-second Reversion:** If error rate breaches the 2.0% threshold or p95 latency spikes above 300ms, Cloud Run instant traffic splitting restores 100% traffic to the known-good revision in under 1.5 seconds.
4. **Authoritative State Machine Synergy:** The Sentinel State Engine strictly requires post-redeploy evaluation evidence (`recovery.verified` from `sentinel-evaluator`) before certifying `RECOVERED`. Canary deployment is the only strategy that provides continuous, statistical comparative evidence against stable baseline metrics.

---

## 5. Local Simulation & Verification

To run the complete 11-step loop locally in parallel with the frontend Mission Control dashboard:

1. **Start Sentinel Backend:**
   ```bash
   cd backend
   uvicorn app.main:app --port 8000
   ```

2. **Start Frontend Dashboard:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Execute End-to-End Recovery Simulation:**
   ```bash
   python sentinel/scripts/run_recovery_simulation.py --backend-url http://localhost:8000 --delay 1.5
   ```

Observe the live HUD in Mission Control: releases transition through canary stages, the incident triggers instant rollback, evidence is scrubbed, gates evaluate the repair MR, and the repaired release certifies recovery!
