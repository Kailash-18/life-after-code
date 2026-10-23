# What's left before submission

Deadline: **Oct 27, 13:00 UTC (18:30 IST)**. Aim to submit Oct 26.
Status as of Oct 23: the loop works **locally** end to end. A seeded bad commit was taken through signed events,
the real backend, both gates and Mission Control, with one incident recovered and one blocked. Nothing has run on GitLab yet.

## Blocks submission

| # | Item | Owner | Done when |
|---|---|---|---|
| 1 | **Move the repo to GitLab.** The rules require a public GitLab project with visible pipeline history; ours is on GitHub. | Team | Public GitLab project; MIT licence shows in About |
| 2 | **Make CI run for real.** Deploy, rollback, evidence and merge all use `--dry-run`. The `${VAR:-default}` values in `variables:` are not GitLab syntax. Jobs only run on `main`, but our default branch is `master`. | Kailash | One pipeline on GitLab deploys a canary, catches the fault, rolls back and collects evidence |
| 3 | **Carry one incident ID through every job.** The evaluator, rollback, evidence and gate jobs must all send the same `incident_id`. | Kailash + Krishna | The backend shows one incident moving through each stage |
| 4 | **Run the Duo flow once on GitLab.** Paste the flow, add a "Pipeline: Failed" trigger, run it on the seeded fault and record the credit cost. | Samvit | The flow opens `duo/fix/inc-…`, and the gates run on that MR |
| 5 | **Fix the backend truth gaps.** `/status` invents health numbers; releases never update; a rollback with no probe result counts as healthy; `/state/rollback`, `/restore` and `/snapshot` are unauthenticated (and rollback reports SUCCESS on failure); `detected_at` is empty; state is in memory and is lost on restart. | Krishna | `/status` and `/releases` come from recorded events only, and the state routes are removed or need auth |
| 6 | **Store the AI analysis.** The flow commits `sentinel/incidents/<id>/analysis.json`; the backend should attach it to the attempt (merge-request webhook or the gate job). Until then, the "AI proposes" section stays empty in live mode. | Krishna | Analysis shows in the incident room |
| 7 | **Deploy.** Run the backend and target app on Cloud Run, and the frontend on hosting with `VITE_API_BASE` set. Keep it up until about Nov 16 for the bonus. | Kailash (+ Samvit for the frontend) | Public links work |
| 8 | **Demo video** (under 3 min, public YouTube), Devpost text, README with run steps. | Unassigned | Submitted |

## Should fix

- **Signing secrets.** Remove the hard-coded HMAC fallbacks (`.gitlab-ci.yml`, `backend/app/config.py`, `emit_event.py`). Set a masked CI variable and a Secret Manager entry instead. (Kailash, Krishna)
- **`docs/verification.md`.** It reports results nobody ran. Replace each row with what was actually observed in items 2–4. (Team)
- **Scope.** Keep the eBPF, FinOps, carbon, multi-region and S3 extras out of the demo; the judges score the end-to-end loop. (Team)

## Done (Samvit, this week)

- Mission Control: 7 consoles, calmer motion, a labelled demo mode, and live mode checked against the real backend.
- Gate jobs fixed in CI; gate verdicts reach the backend through `report_gate_verdict.py`.
- The Integrity Gate now protects nested `app/tests/`.
- Duo flow written (`.gitlab/duo/flows/`) with wiring tests; setup steps in `docs/duo-flow.md`.
