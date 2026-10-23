# Sentinel Demo Target App (`app/`)

Lightweight FastAPI orders microservice deployed as the target workload under test for Project Sentinel.

## Endpoints
* `GET /healthz` — Rapid liveness probe reporting service status and version.
* `GET /metrics` — Prometheus metrics (latency histogram, error rates, request counts) scraped by Sentinel's Health Evaluator (`sentinel/scripts/evaluator.py`).
* `POST /api/v1/orders` — Places a new order, calculates tier discounts.
* `GET /api/v1/orders` — Lists placed orders.
* `GET /api/v1/orders/{id}` — Retrieves order detail.

## Reproducible Fault (demo)

The fault is a **normal code commit**, not a runtime toggle, so the AI's regression test can
fail on the broken commit and pass on the fix (acceptance #5/#6).

- Healthy code: `calculate_discount` normalises tier names (`"Premium"` → `premium`) and
  gives unknown tiers no discount.
- Faulty commit, `refactor(orders): simplify tier discount lookup`
  ([`docs/demo/fault-discount-lookup.patch`](../docs/demo/fault-discount-lookup.patch)):
  drops the normalisation, so `TIER_RATES["Premium"]` raises `KeyError` and the request returns **500**.
- The existing unit tests use lowercase tiers, so **CI stays green** and the bug reaches the canary.
  `/healthz` also stays `ok`. Only real traffic exposes it.

Apply it during the demo:

```bash
git apply docs/demo/fault-discount-lookup.patch
git commit -am "refactor(orders): simplify tier discount lookup"
git push
```

### Synthetic load profile (for the health evaluator)

`POST /api/v1/orders` with `customer_tier` drawn from:

| tier | weight |
|---|---|
| `standard` | 40% |
| `premium` | 25% |
| `Premium` | 15% |
| `enterprise` | 10% |
| `ENTERPRISE` | 10% |

Measured locally with 300 requests: healthy commit error rate **0.000**, faulty commit
**0.257** (77/300 → 500; `http_errors_total` agrees). Any load without mixed-case tiers will
**not** detect the fault.

### Regression tests

Generated tests go in `tests/regressions/test_inc_<id>.py` at the repo root.
`tests/regressions/conftest.py` puts `app/` on the import path and provides a `client`
fixture. Verified with `sentinel/scripts/regression_proof.py`: a test posting
`customer_tier: "Premium"` fails with `AssertionError` on the faulty commit and passes on the fix
(verdict PROVEN), and the Integrity Gate passes that fix (0 blocking findings).

## Running Locally
```bash
cd app
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Running Tests
```bash
pytest --junitxml=junit.xml --cov=app
```
