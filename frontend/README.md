# Sentinel Mission Control (frontend)

Mission Control for Project Sentinel: seven read-only consoles over a 3D core whose colour and motion follow
the recorded state. React + Vite + TypeScript, Three.js via React Three Fiber (light bloom), GSAP ScrollTrigger
for one-time fade-ins. Motion is deliberately calm: native scrolling, flat cards, no custom cursor, and the core
only reacts when the recorded state changes. `prefers-reduced-motion` turns the remaining motion off.

## Run

```bash
npm install
npm run dev                 # http://localhost:5173 — /api is proxied to http://localhost:8000
```

- **Live:** reads `GET /api/v1/status`, `/releases`, `/incidents`, `/incidents/{id}` and `/incidents/{id}/timeline`.
- **Demo scenario:** `http://localhost:5173/?demo` plays one incident through every recovery stage
  (`?demo=fail` stops at verification, `&step=6` sets seconds per stage). A permanent banner labels it as scripted data,
  with Replay / failure path / Exit. If the API is unreachable, the page offers the demo instead of faking data.

Production: `VITE_API_BASE=https://<backend> VITE_GITLAB_PROJECT_URL=https://gitlab.com/<group>/<project> npm run build`.

## Consoles

Hash routes, so the build works on any static host. `⌘K` / `Ctrl+K` / `/` opens the command palette (also the mobile menu); `1`–`6` jump between consoles.

| Route | Console | Reads |
|---|---|---|
| `#/` | Mission Control: pulse, the loop, module tiles, outcome | status, releases, incidents |
| `#/rollout` | Release line, canary ladder per release, evaluator verdict table, rollbacks | releases, `deploy.canary_started` / `evaluator.verdict` / `rollback.*` events |
| `#/incidents` | Every incident with filters and a 9-segment loop bar | incidents + per-incident timelines |
| `#/incidents/:id` | Incident room: stages, sealed evidence, AI analysis (incl. `no_fix_found`), repair MR, regression proof, Integrity Gate findings, attempts, outcome, timeline | incident detail + timeline |
| `#/gates` | Regression-proof rules, the 9 Integrity Gate rules with hit counts, every recorded verdict and finding | gate results on attempts, gate events |
| `#/ledger` | Every event, time strip, filters by kind / incident / text | merged incident timelines |
| `#/system` | Data source, healthz, per-endpoint health, authority table, the 11-step loop with owners and events seen | `/api/v1/healthz` + poll results |

The demo (`?demo`) carries three incidents: one recovered three days ago, one escalated yesterday (repair blocked by RULE_01/RULE_02, second attempt `no_fix_found`), and one that plays live.

## What reacts to what

| Backend state | Reactor core |
|---|---|
| healthy | calm cyan core, slow particle rings |
| canary | amber, a wireframe satellite sized by the candidate's traffic % |
| DETECTED | rose, the core spikes and shatters into shards, camera shake, chromatic split, screen flash |
| rolled back / evidence | orange, shards pulled back in |
| AI investigating / proposing | violet scanning ring (advisory) |
| verifying / merged | cyan, rings speed up |
| redeploying | mint |
| RECOVERED | core turns green and settles — only when the incident record says RECOVERED |
| failure statuses | rose, fractured, frozen |

The nine rings orbiting the core are the nine recovery stages, coloured by their recorded state.

## Truth rules

- AI output (facts, hypotheses, proposed fix) is violet, hatched, and labelled advisory. It is never shown as proof.
- Stage cards: *Sourced* only when a timeline event backs the stage; *Blocked* stages after a failure are marked derived.
- Proof stamps show only what each job recorded (PASS / BLOCKED / WARN / PENDING).
- The trace draws only recorded readings. Stale data is greyed and the HUD says how old it is.
- Respects `prefers-reduced-motion`; drops effects automatically on slow GPUs; falls back to a static glow without WebGL.
