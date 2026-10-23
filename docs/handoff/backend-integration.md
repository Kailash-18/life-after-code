# Backend integration handoff (Krishna → Kailash, Samvit)

Everything here is implemented and tested on branch `feat/backend-r4-r9` unless marked
**UNVERIFIED** (written against docs, never run in our GitLab / Google Cloud).
Details: [`docs/backend.md`](../backend.md). Contracts: [`docs/contracts/`](../contracts/).

## 1. Deploy the backend to Cloud Run (Kailash) — UNVERIFIED commands

Build from the repository root (the image must contain the event + analysis schemas):

```bash
# one-time secrets (Secret Manager)
openssl rand -hex 32 | gcloud secrets create sentinel-hmac-secret --data-file=-
openssl rand -hex 24 | gcloud secrets create sentinel-gitlab-webhook-secret --data-file=-

# build + push (Docker-in-Docker or Buildah in CI; Kaniko is unmaintained)
docker build -f backend/Dockerfile -t "$REGION-docker.pkg.dev/$PROJECT/sentinel/backend:$CI_COMMIT_SHA" .
docker push "$REGION-docker.pkg.dev/$PROJECT/sentinel/backend:$CI_COMMIT_SHA"

# deploy: ONE instance, because storage is SQLite inside the container (see below)
gcloud run deploy sentinel-backend \
  --image "$REGION-docker.pkg.dev/$PROJECT/sentinel/backend:$CI_COMMIT_SHA" \
  --region "$REGION" --allow-unauthenticated \
  --min-instances 1 --max-instances 1 \
  --set-secrets SENTINEL_HMAC_SECRET=sentinel-hmac-secret:latest,GITLAB_WEBHOOK_SECRET=sentinel-gitlab-webhook-secret:latest \
  --set-env-vars CORS_ORIGINS="https://<mission-control-url>"

# check
curl -fsS "$SENTINEL_API_URL/api/v1/healthz"
```

The container **refuses to start** with development secrets (`SENTINEL_ENV=production` is
baked into the image). `--allow-unauthenticated` is fine: reads are public by design and
writes need the HMAC signature or the webhook token.

**Persistence caveat:** SQLite lives in the container and is lost on restart. Until the team
picks Firestore / Cloud SQL, keep `--max-instances 1` and do not redeploy the backend between
the demo recording steps.

## 2. CI variables (Kailash)

| Variable | Value | Protected + masked |
|---|---|---|
| `SENTINEL_API_URL` | Cloud Run URL | no |
| `SENTINEL_HMAC_SECRET` | same value as the `sentinel-hmac-secret` secret | **yes** |

Only jobs that emit events need it. Never `echo` it; `emit_event.py` never prints it.

## 3. GitLab webhook (Kailash or whoever has Maintainer)

Project → Settings → Webhooks:
- URL: `$SENTINEL_API_URL/api/v1/webhooks/gitlab`
- Secret token: the `sentinel-gitlab-webhook-secret` value
- Triggers: **Merge request events** (required: drives REPAIR_PROPOSED / MERGED), Pipeline events, Job events

## 4. Which job sends which event (Kailash)

Use `python backend/scripts/emit_event.py` (stdlib only, retries, fails the job if Sentinel
rejects the event). Add `--incident-id "$INCIDENT_ID"` once an incident exists.

| Loop step (§A3) | Job | Command |
|---|---|---|
| 1 push | build | `--type pipeline.started --data '{"version":"'$VERSION'"}'` |
| 2 canary 0% / steps | deploy | `--type deploy.canary_started --data '{"traffic_percent":10,"revision_name":"'$REV'"}'` (repeat per step) |
| 3 evaluate | evaluator | `--type evaluator.verdict --source sentinel/scripts/evaluator.py --data '{"verdict":"PASS\|FAIL","target":"candidate","traffic_percent":10,"error_rate":0.26,"p95_ms":120,"sample_size":300}'` |
| 4 breach | evaluator | `--type incident.detected --incident-id inc-$CI_PIPELINE_ID --source sentinel/scripts/evaluator.py --data '{"breached_thresholds":["error_rate 0.26 > 0.02"]}'` |
| 4 rollback + probe | rollback | `--type rollback.completed --data '{"post_rollback_probe_ok":true}'` |
| 5 evidence | evidence | `--type evidence.collected --artifact-url "$BUNDLE_URL" --data '{"evidence_sha256":"'$SHA256'"}'` |
| 6 flow start (if CI starts it) | dispatch | `--type flow.started --data '{"flow_session_id":"'$WORKFLOW_ID'"}'` |
| 8 regression proof | MR pipeline | `--type regression_proof.verdict --from-regression-proof proof.json --artifact-url "$CI_JOB_URL"` |
| 8 Integrity Gate | MR pipeline | `--type integrity_gate.verdict --from-integrity-gate integrity.json --artifact-url "$CI_JOB_URL"` |
| 10 redeploy | deploy (fix) | `--type deploy.canary_started --data '{"traffic_percent":10}'` |
| 11 recovered | evaluator (fix, 100%) | `--type recovery.verified --source sentinel/scripts/evaluator.py --data '{"verdict":"PASS","target":"candidate","traffic_percent":100,"error_rate":0.001,"p95_ms":35,"sample_size":600}'` |

**Incident ids are optional.** The backend opens `inc-<pipeline_id>` from the evaluator's FAIL
and links later events by pipeline / commit SHA / alias (see "Incident correlation" in
`docs/backend.md`). Your current scripts work as they are; tested with your real `emit_event.py`.

`repair.proposed` and `merge.completed` come from the **MR webhook** automatically; CI may
send them too (duplicates are harmless). The repair MR pipeline runs on the MR, so pass the
incident id to it (e.g. parse it from `CI_MERGE_REQUEST_SOURCE_BRANCH_NAME` = `duo/fix/<incident_id>`).

**The evaluator's synthetic load must include mixed-case tiers** (`Premium`, `ENTERPRISE`),
or the seeded fault is invisible. Profile: [`app/README.md`](../../app/README.md).

## 5. Mission Control (Samvit)

- Poll `GET /api/v1/status` and `GET /api/v1/incidents/{id}/timeline` (5 s is fine).
- `/status` fields may be **null** before the first evaluator measurement: show "unknown", not 0.
- Timeline events have `rejected: true` + `summary` when Sentinel refused something (great for
  the "AI tried to declare recovery and was refused" moment). Use `evidence_url` for links.
- `recovery_attempts[].analysis` carries `advisory: true`: label it as AI opinion, not proof.
- Errors: read `error.code` / `error.message` (top-level `error`).
- Every response shape is checked against `openapi.yaml` by `backend/tests/test_contract_responses.py`.

## 6. Duo flow (Samvit)

- Repair branch **must** be `duo/fix/<incident_id>` (e.g. `duo/fix/inc-1234`), or the webhook can't link the MR.
- Write `sentinel/incidents/<incident_id>/analysis.json` (validated against `analysis.schema.json`; `incident_id` must match).
- Regression tests: `tests/regressions/test_inc_<id>.py` using the existing `client` fixture
  from `tests/regressions/conftest.py` (do not edit it: the Integrity Gate blocks that).
- After spike S1, tell Krishna which dispatch route works. Backend side is ready for
  `SENTINEL_FLOW_DISPATCH_MODE=gitlab_api` (+ `GITLAB_PROJECT_ID`, `GITLAB_FLOW_TOKEN`,
  `SENTINEL_FLOW_DEFINITION`) — **UNVERIFIED**. Otherwise CI starts the flow and sends `flow.started`.

## 7. Open decisions / known gaps

- Persistence (Firestore vs Cloud SQL): not implemented; SQLite + single instance until decided.
- `ruff check .` in CI fails on 51 pre-existing findings in `sentinel/scripts/` and `tests/` (Samvit's files).
- `docs/demo/fault-discount-lookup.patch` is in the repo, so the flow could read it. Decide
  whether to keep it there for transparency or move it out before recording.
- Hackathon requires a **public GitLab** project; `origin` is currently GitHub.
