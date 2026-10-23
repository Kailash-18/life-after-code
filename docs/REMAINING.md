# What's left before submission

Deadline: **Oct 27, 13:00 UTC (18:30 IST)**. Aim to submit Oct 26.
Status as of Oct 23: the loop works **locally** end to end. A seeded bad commit was taken through signed events,
the real backend, both gates and Mission Control, with one incident recovered and one blocked. Nothing has run on GitLab yet.

## Blocks submission

| # | Item | Owner | Done when |
|---|---|---|---|
| 1 | **Move the repo to GitLab.** The rules require a public GitLab project with visible pipeline history; ours is on GitHub. | Team | Public GitLab project; MIT licence shows in About |
| 2 | **Make CI run for real.** Deploy, rollback, evidence and merge all use `--dry-run`. The `${VAR:-default}` values in `variables:` are not GitLab syntax. Jobs only run on `main`, but our default branch is `master`. | Kailash | One pipeline on GitLab deploys a canary, catches the fault, rolls back and collects evidence |
| 3 | **Carry one incident ID through every job.** The evaluator, rollback, evidence and gate jobs must all send the same `incident_id`. | Kailash + Krishna | The backend shows one incident moving through each stage <br>**Backend side done (Krishna, Oct 24):** jobs no longer need to pass the id. The backend opens `inc-<pipeline_id>` from the evaluator FAIL and links rollback, evidence (its own id becomes an alias), the `duo/fix/*` MR, gates, merge and the redeploy on the merge commit. Proven with Kailash's real `emit_event.py` in `backend/tests/test_team_pipeline_integration.py`. Still needed from CI: real (non `--dry-run`) jobs and the MR webhook configured. |
| 4 | **Run the Duo flow once on GitLab.** Paste the flow, add a "Pipeline: Failed" trigger, run it on the seeded fault and record the credit cost. | Samvit | The flow opens `duo/fix/inc-…`, and the gates run on that MR |
| 5 | **Fix the backend truth gaps.** `/status` invents health numbers; releases never update; a rollback with no probe result counts as healthy; `/state/rollback`, `/restore` and `/snapshot` are unauthenticated (and rollback reports SUCCESS on failure); `detected_at` is empty; state is in memory and is lost on restart. | Krishna | `/status` and `/releases` come from recorded events only, and the state routes are removed or need auth <br>**Done (Krishna, Oct 24)** except restart persistence: `/status`, `/releases` from events only; rollback needs `post_rollback_probe_ok`; `detected_at` set; `/state/*` writes need the CI HMAC and rollback reports `STATE_RESTORED_TRAFFIC_NOT_SHIFTED` unless gcloud really moved traffic. Storage is SQLite in the container: still lost on restart until Firestore/Cloud SQL is decided. |
| 6 | **Store the AI analysis.** The flow commits `sentinel/incidents/<id>/analysis.json`; the backend should attach it to the attempt (merge-request webhook or the gate job). Until then, the "AI proposes" section stays empty in live mode. | Krishna | Analysis shows in the incident room <br>**Done (Krishna, Oct 24)**: on the `duo/fix/<id>` MR webhook (or `repair.proposed`) the backend fetches `analysis.json` at the fix SHA, validates it and stores it as advisory. Needs `GITLAB_PROJECT_ID` + `GITLAB_READ_TOKEN` on the backend. |
| 7 | **Deploy.** Run the backend and target app on Cloud Run, and the frontend on hosting with `VITE_API_BASE` set. Keep it up until about Nov 16 for the bonus. | Kailash (+ Samvit for the frontend) | Public links work |
| 8 | **Demo video** (under 3 min, public YouTube), Devpost text, README with run steps. | Unassigned | Submitted |

## Local end-to-end run with the real scripts (Krishna, Oct 24)

Demo app (healthy + seeded fault), the real `evaluator.py`, `rollback.py`, `evidence_collector.py`,
`regression_proof.py`, `integrity_gate.py` and `report_gate_verdict.py`, against the real backend.
Only GitLab itself (MR open/merge webhooks) was simulated.

Result: one incident went DETECTED → ROLLED_BACK → EVIDENCE_COLLECTED → (inferred) INVESTIGATING →
REPAIR_PROPOSED → VERIFYING → MERGED → REDEPLOYING → RECOVERED, and a healthy release opened no incident.

Found and fixed on the way (Kailash, please review):
- `sentinel/policy.yaml` POST probe used `sku`/`tier`, which the demo app rejects (422): even the
  healthy app failed with 48 % errors. Now `item_id`/`customer_tier`, with mixed-case tiers so the
  seeded fault is visible (faulty release: 16.7 % errors).
- `evaluator.py`: the candidate is probed first and paid client warm-up, so its p95 was ~15× the
  stable one and every release failed the latency ratio. Added unmeasured warm-up requests. The
  latency ratio and the Mann-Whitney test now also need a p95 slowdown > `latency_ratio_min_delta_ms`
  (50 ms). Before: healthy release falsely failed 4/12 runs; after: 25/25 PASS, faulty 10/10 FAIL.

Still open (Kailash's scripts, not changed):
- `rollback.py` reports `success` with mode `fallback_local` when gcloud fails, and hard-codes
  `post_rollback_probe_ok: true` in simulation mode: the backend would record a rollback that did not happen.
- `auto_merge.py` falls back to a "simulated merge" with a hard-coded SHA when the GitLab API fails, and
  still emits `merge.completed`.

## Backend audit (Krishna, Oct 24) — fixed

- **Backend container could not start:** the state store created `artifacts/state_cache` at import, which the
  non-root image user cannot write → `PermissionError`. Cache dir is now `SENTINEL_STATE_CACHE_DIR`
  (`/tmp/sentinel-state` in the image) and an unwritable path disables the cache instead of crashing.
- **Snapshots were always empty** (the incident proxy serialised as `{}`), and **restore changed nothing**
  while reporting success. Snapshots now hold the real incidents; restore writes them back.
- `/state/storage` claimed S3, versioning and DynamoDB locking that were never checked; now reports what is real.
- Snapshot files grew without limit (Cloud Run disk is memory): one per state change, capped at 50.
- A deploy or a stale evaluator FAIL for a commit other than the fix no longer moves the incident.
- An incident whose flow never opens a repair MR now times out (`SENTINEL_REPAIR_TIMEOUT_MINUTES`, 60).
- Background tasks and requests can no longer overwrite each other's incident updates (one lock).
- A commit that fails again after its incident closed opens a fresh incident instead of being lost.
- GitLab pipeline/job webhooks now appear on the incident timeline; event bodies over 256 KB are refused.

## Should fix

- **Signing secrets.** Remove the hard-coded HMAC fallbacks (`.gitlab-ci.yml`, `backend/app/config.py`, `emit_event.py`). Set a masked CI variable and a Secret Manager entry instead. (Kailash, Krishna)
- **`docs/verification.md`.** It reports results nobody ran. Replace each row with what was actually observed in items 2–4. (Team)
- **Scope.** Keep the eBPF, FinOps, carbon, multi-region and S3 extras out of the demo; the judges score the end-to-end loop. (Team)

## Done (Samvit, this week)

- Mission Control: 7 consoles, calmer motion, a labelled demo mode, and live mode checked against the real backend.
- Gate jobs fixed in CI; gate verdicts reach the backend through `report_gate_verdict.py`.
- The Integrity Gate now protects nested `app/tests/`.
- Duo flow written (`.gitlab/duo/flows/`) with wiring tests; setup steps in `docs/duo-flow.md`.
