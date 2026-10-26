# Sentinel Backend

The backend records truth; it does not create it. It ingests signed CI events and GitLab
webhooks, keeps the state of releases and recovery attempts, starts the investigation flow,
and serves read-only data to Mission Control. A status only moves forward when the
authoritative source in §A5 proves it. An AI message saying "fixed" is never proof.

Contracts: [`docs/contracts/openapi.yaml`](contracts/openapi.yaml) ·
[`docs/contracts/event.schema.json`](contracts/event.schema.json)

## Status (what is implemented)

| Task | State | Notes |
|---|---|---|
| R1 skeleton | Implemented | FastAPI, env config, `/api/v1/healthz`, Dockerfile (repo-root build context) |
| R2 persistence | Implemented | SQLite (default) and in-memory. Firestore/Postgres **not implemented** (team decision pending) |
| R3 ingest | Implemented | HMAC, ±300 s replay window, schema validation (fail closed), idempotency on `(job_id, type)` plus `traffic_percent` when present (one job may step 10→50→100 %), GitLab webhook token |
| R4 state machine | Implemented | No skipped states; each transition needs its §A5 evidence (table below) |
| R5 flow dispatch | Implemented, **API route unverified** | `disabled` (default) or `gitlab_api`; exactly once per attempt; deadline → `TIMED_OUT` |
| R6 read APIs | Implemented | `/status`, `/releases`, `/incidents`, `/incidents/{id}/timeline`; no seeded or placeholder data |
| R7 evidence + redaction | Implemented | Evidence URL + SHA-256 stored; sensitive keys redacted; credential-like values rejected (events) or masked (webhooks) |
| R8 access control | Implemented | Writes need the CI HMAC (or GitLab token for webhooks); browsers get GET-only CORS |
| Analysis ingestion | Implemented, **GitLab call unverified** | On repair MR open (webhook) or `repair.proposed`, fetches `sentinel/incidents/<id>/analysis.json` at the fix SHA, validates against `analysis.schema.json`, stores it with `advisory: true`. Never changes state. Invalid → `analysis.rejected` in the timeline |

## Evidence required per transition

| Transition | Event | Required evidence (else 409/422, nothing changes) |
|---|---|---|
| → DETECTED | `incident.detected` | `data.breached_thresholds[]` (measured) |
| → ROLLED_BACK / ROLLBACK_FAILED | `rollback.completed` | `data.post_rollback_probe_ok` true / false |
| → EVIDENCE_COLLECTED | `evidence.collected` | `artifact_url` + `data.evidence_sha256` |
| → INVESTIGATING | `flow.started` (CI, or backend dispatcher) | `data.flow_session_id`; sets `deadline_at` |
| → INVESTIGATION_FAILED | `flow.completed` with `verdict: FAIL`, or dispatch error | reason recorded |
| → TIMED_OUT | none: deadline passes while EVIDENCE_COLLECTED (no MR / flow) or INVESTIGATING | checked on every read and write |
| → REPAIR_PROPOSED | `repair.proposed`, or GitLab MR `open` on `duo/fix/<incident_id>` | `mr_iid` + `fix_sha` |
| → VERIFYING / VERIFICATION_FAILED | `regression_proof.verdict`, `integrity_gate.verdict` | PASS proof needs `broken_run` (failed, AssertionError) **and** `fix_run` (passed) |
| → MERGED | `merge.completed`, or GitLab MR `merge` | regression proven both ways **and** Integrity Gate PASS. Otherwise → **ESCALATED** |
| → REDEPLOYING | `deploy.canary_started` / `redeploy.completed` | the deployed commit is the fix or merge commit (a deploy of any other commit is only recorded) |
| → RECOVERED | `recovery.verified` | source contains `evaluator`, `verdict: PASS`, `commit_sha` = fix SHA, `traffic_percent` 100 if sent. The evaluator job id is recorded on the release's deployment and in the timeline |
| → REDEPLOY_UNHEALTHY | `recovery.verified` / `evaluator.verdict` FAIL while REDEPLOYING | reason recorded |

Rejected events (non-retryable) are still written to the timeline with `rejected: true`
so the dashboard can show what was refused and why. `UNKNOWN_INCIDENT` is **retryable**:
the idempotency key is released so CI can resend after `incident.detected` arrives.

Release-level events (`pipeline.started`, `deploy.canary_started`, `evaluator.verdict`, ...)
without an `incident_id` update releases, deployments and health samples, which is what `/status` shows.
A release is a commit: the backend always uses `rel-<first 12 chars of commit_sha>` as the release id and ignores a CI-sent `release_id` when `commit_sha` is present (`canary_deploy.py` sends the placeholder `rel-candidate-001` for every release).

## Incident correlation (CI jobs do not need to know the incident id)

The team's pipeline does not carry one incident id through every job, so the backend links events itself:

| Situation | What the backend does |
|---|---|
| `evaluator.verdict` FAIL (source contains `evaluator`, `target: candidate`, non-empty `breached_thresholds`) and no open incident | Opens `inc-<pipeline_id>` in DETECTED: the evaluator's measurement is the detection (§A5) |
| Event without `incident_id` | Linked to the open incident of the same `pipeline_id`, or whose broken / fix / merge commit equals `commit_sha` (or `data.fix_sha`) |
| Event with an unknown `incident_id` (e.g. the evidence job's `inc-<timestamp>`) | Recorded as an alias of the open incident it correlates with; `duo/fix/<alias>` branches resolve too |
| Second `incident.detected` / second `merge.completed` | No transition; only thresholds / merge SHAs are learnt |
| Repair MR opens while the incident is EVIDENCE_COLLECTED (flow started by a GitLab trigger, so no `flow.started` arrived) | Records an explicit, labelled `flow.started` ("inferred from repair MR") then REPAIR_PROPOSED |
| Merge (auto-merge job or MR webhook) | The merge/squash commit becomes part of the fix release, because the redeploy pipeline runs on it |
| `evaluator.verdict` PASS at `traffic_percent: 100` for the fix/merge commit while REDEPLOYING | RECOVERED (same authority as `recovery.verified`) |

Recovery still requires the evaluator, PASS, 100 % traffic and a commit that is the fix release.
Covered by `backend/tests/test_team_pipeline_integration.py`, which drives the backend with the
team's real `sentinel/scripts/emit_event.py` and `report_gate_verdict.py`.

## Environment variables

| Variable | Purpose | Default | Production |
|---|---|---|---|
| `SENTINEL_ENV` | `development` / `production` | `development` (`production` in the Docker image) | — |
| `PORT` | HTTP port (Cloud Run sets it) | `8000` | — |
| `SENTINEL_HMAC_SECRET` | Shared secret for CI event signatures | dev value | **Required**, 32+ random chars; startup refuses the dev value |
| `GITLAB_WEBHOOK_SECRET` | Expected `X-Gitlab-Token` | dev value | **Required** |
| `CORS_ORIGINS` | Comma-separated dashboard origins | `http://localhost:3000,http://localhost:5173` | Set to the Mission Control URL |
| `SENTINEL_PERSISTENCE_BACKEND` | `sqlite` or `memory` | `sqlite` | — |
| `SENTINEL_SQLITE_PATH` | SQLite file | `sentinel.db` (`/tmp/sentinel.db` in the image) | See "Cloud Run caveat" |
| `SENTINEL_EVENT_SCHEMA_PATH` | Event contract location | auto-detected | Set by the Dockerfile |
| `SENTINEL_FLOW_DISPATCH_MODE` | `disabled` or `gitlab_api` | `disabled` | Choose after spike S1 |
| `SENTINEL_FLOW_TIMEOUT_MINUTES` | Investigation deadline | `30` | — |
| `SENTINEL_REPAIR_TIMEOUT_MINUTES` | Deadline for a repair MR / `flow.started` after evidence is collected (EVIDENCE_COLLECTED → TIMED_OUT) | `60` | — |
| `SENTINEL_STATE_CACHE_DIR` | Writable dir for state snapshots (Kailash's state store). Unwritable → cache disabled, never a crash | `artifacts/state_cache` (`/tmp/sentinel-state` in the image) | — |
| `SENTINEL_STATE_CACHE_MAX` | Snapshot files kept locally (Cloud Run's filesystem is memory) | `50` | — |
| `GITLAB_API_URL` | GitLab API base | `https://gitlab.com/api/v4` | — |
| `GITLAB_PROJECT_ID` | Project the flow runs in | — | Required for `gitlab_api` |
| `GITLAB_FLOW_TOKEN` | Token for the Flows API (Secret Manager) | — | Required for `gitlab_api`; never logged or sent to the flow |
| `GITLAB_READ_TOKEN` | Read-only token (`read_api`) to fetch `analysis.json` | falls back to `GITLAB_FLOW_TOKEN` | Optional; without it analysis ingestion is skipped |
| `SENTINEL_FLOW_DEFINITION` | `workflow_definition` of the custom flow | — | Required for `gitlab_api` (value unknown until S1) |

## Signing events (for CI)

```
body      = the exact JSON bytes you POST
signature = "sha256=" + hex(HMAC_SHA256(SENTINEL_HMAC_SECRET, body))
headers   = X-Sentinel-Signature: <signature>
            X-Sentinel-Timestamp: <same value as body.sent_at, ISO-8601 UTC>
```

```python
import hashlib, hmac, json, os, datetime, urllib.request
now = datetime.datetime.now(datetime.UTC).isoformat()
event = {"type": "incident.detected", "source": "sentinel/scripts/evaluator.py",
         "pipeline_id": os.environ["CI_PIPELINE_ID"], "job_id": os.environ["CI_JOB_ID"],
         "commit_sha": os.environ["CI_COMMIT_SHA"], "sent_at": now,
         "data": {"breached_thresholds": ["error_rate 0.08 > 0.02"]}}
body = json.dumps(event).encode()
sig = "sha256=" + hmac.new(os.environ["SENTINEL_HMAC_SECRET"].encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(os.environ["SENTINEL_API_URL"] + "/api/v1/events", data=body, method="POST",
      headers={"Content-Type": "application/json", "X-Sentinel-Signature": sig, "X-Sentinel-Timestamp": now})
urllib.request.urlopen(req)
```

## End-to-end smoke test (dev only)

`backend/scripts/smoke_e2e.py` drives a **running** backend through the whole loop over HTTP
with signed synthetic events and checks `/status`, the incident and its timeline
(18 checks, exit 0 = all passed). Do not point it at the demo deployment: it creates a fake incident.

```bash
SENTINEL_API_URL=http://localhost:8000 SENTINEL_HMAC_SECRET=... python backend/scripts/smoke_e2e.py
```

## CI client

`backend/scripts/emit_event.py` signs and sends one event from a CI job (stdlib only), retries
on network errors / 5xx / retryable rejections, and converts `regression_proof.py` and
`integrity_gate.py` JSON reports (`--from-regression-proof`, `--from-integrity-gate`).
It exits non-zero when Sentinel rejects an event so the pipeline never looks green by mistake.
Per-stage commands: [`docs/handoff/backend-integration.md`](handoff/backend-integration.md).

## Error format

All errors are `{"error": {"code", "message", "retryable"}}`. The same object is repeated
under `detail` for older clients; new code should read `error`.

## Running locally

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # Swagger UI at http://localhost:8000/docs
pytest -v
```

## Docker

Build from the repository root so the event contract is copied into the image:

```bash
docker build -f backend/Dockerfile -t sentinel-backend .
docker run -p 8000:8000 \
  -e SENTINEL_HMAC_SECRET="$(openssl rand -hex 32)" \
  -e GITLAB_WEBHOOK_SECRET="<webhook token>" \
  sentinel-backend
```

## Cloud Run caveat (open team decision)

SQLite lives in the container's memory-backed filesystem: data is lost on restart and is
not shared between instances. Until Firestore/Postgres is decided and implemented, deploy
with `--min-instances=1 --max-instances=1` and accept that a restart clears history.

## State snapshots (`/api/v1/state/*`, Kailash's store)

- Every state **change** writes a snapshot of all incidents (S3 if configured, else the local cache).
- `POST /state/snapshot|restore|rollback` need the CI HMAC signature.
- `restore` verifies the snapshot SHA-256 and writes the incidents back into the repository.
  It restores incidents only (not releases, events or correlations).
- `rollback` reports `SUCCESS` only when gcloud really moved traffic and the probe passed.
- Without S3 (boto3 is not in the image) snapshots live in the container and do **not** survive a restart.

## Known limitations

- `source` is self-declared inside a signed event. Anyone with the CI HMAC secret can claim
  to be the evaluator, so the secret must be a protected + masked variable scoped to the jobs that emit events.
- The Flows API dispatch route (`gitlab_api`) is implemented against the documented endpoint
  but **not verified** in our GitLab namespace (token type and `workflow_definition` unknown).
- Analysis `evidence_ref`s are not checked against the bundle's contents (acceptance #4 is
  judged by reading the analysis next to the bundle).
