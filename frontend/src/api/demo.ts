/**
 * DEMO SCENARIO — scripted data, not telemetry.
 * The interface shows a permanent "Demo scenario" banner whenever this is the source,
 * and never mixes it with live API data.
 *
 * Three incidents:
 *   inc-demo-001  three days ago  latency regression in 1.4.1, recovered by 1.4.2
 *   inc-demo-002  yesterday       1.4.3 crash; repair blocked by the Integrity Gate, second attempt
 *                                 found no fix, escalated to a person
 *   inc-demo-003  now             plays through every recovery stage on a timer (1.5.0 → 1.5.1);
 *                                 `fail` stops it at verification instead
 */
import type { GateResult, IncidentDetail, Release, Snapshot, SystemStatus, TestResult, TimelineEvent } from './types';

export const PHASES = ['HEALTHY', 'CANARY', 'DETECTED', 'ROLLED_BACK', 'EVIDENCE_COLLECTED', 'INVESTIGATING', 'REPAIR_PROPOSED', 'VERIFYING', 'MERGED', 'REDEPLOYING', 'RECOVERED'] as const;

const iso = (ms: number) => new Date(ms).toISOString();
const H = 3_600_000;
const R = (id: string, version: string, sha: string, status: string, good: boolean, at: number, rev: string, pipe: number): Release =>
  ({ id, version, commit_sha: sha, status, known_good: good, created_at: iso(at), revision_name: rev, pipeline_id: String(pipe) });

type EvOpt = { release?: string; incident?: string; sha?: string; pipeline?: number; evidence?: string; data?: Record<string, unknown> };
let seq = 0;
const E = (at: number, type: string, source: string, job: number, summary: string, o: EvOpt = {}): TimelineEvent => ({
  id: `evt-${type}-${at}-${seq++}`, type, source, job: String(job), at: iso(at), summary,
  release_id: o.release, incident_id: o.incident, commit_sha: o.sha, pipeline_id: o.pipeline !== undefined ? String(o.pipeline) : undefined,
  evidence_url: o.evidence, data: o.data ?? {},
});
const SRC = {
  deploy: 'gitlab-ci/deploy-candidate', evalr: 'sentinel/scripts/evaluator.py', detect: 'gitlab-ci/evaluate-candidate',
  rollback: 'gitlab-ci/rollback', evidence: 'sentinel/scripts/evidence.py', flow: 'duo-flow/sentinel-investigate',
  proof: 'sentinel/scripts/regression_proof.py', integrity: 'sentinel/scripts/integrity_gate.py', merge: 'gitlab-ci/merge-gate',
  pipe: 'gitlab-ci/pipeline',
};
const canary = (at: number, rel: Release, pct: number, job: number, inc?: string) =>
  E(at, 'deploy.canary_started', SRC.deploy, job, `Release ${rel.version} deployed as candidate with ${pct}% of traffic.`,
    { release: rel.id, incident: inc, sha: rel.commit_sha, pipeline: +rel.pipeline_id!, data: { traffic_percent: pct, revision_name: rel.revision_name, target: 'candidate' } });
const verdict = (at: number, rel: Release, pct: number, job: number, v: 'PASS' | 'FAIL' | 'IN_PROGRESS', er: number, p95: number, n: number, inc?: string, breached: string[] = []) =>
  E(at, 'evaluator.verdict', SRC.evalr, job,
    v === 'PASS' ? `Candidate ${rel.version} within thresholds at ${pct}%: error rate ${(er * 100).toFixed(2)}%, p95 ${p95} ms.`
      : v === 'FAIL' ? `Candidate ${rel.version} failed at ${pct}%: ${breached.join('; ')}.`
      : `Candidate ${rel.version} sampling at ${pct}%: ${n} requests so far.`,
    { release: rel.id, incident: inc, sha: rel.commit_sha, pipeline: +rel.pipeline_id!, evidence: v === 'IN_PROGRESS' ? undefined : `#evaluator-${job}`,
      data: { verdict: v, target: 'candidate', traffic_percent: pct, error_rate: er, p95_ms: p95, sample_size: n, breached_thresholds: breached, revision_name: rel.revision_name } });

/* ---------------- History (fixed, relative to t0) ---------------- */
function history(t0: number) {
  const a = t0 - 72 * H, b = t0 - 20 * H;
  const r140 = R('rel-r-140', '1.4.0', 'b71c0e2', 'STABLE', true, t0 - 120 * H, 'orders-00011-kit', 8811);
  const r141 = R('rel-r-141', '1.4.1', '9e4d2c7', 'ROLLED_BACK', false, a - 20 * 60e3, 'orders-00012-lum', 8840);
  const r142 = R('rel-r-142', '1.4.2', '5f0a9b3', 'STABLE', true, a + 70 * 60e3, 'orders-00014-ved', 8856);
  const r143 = R('rel-r-143', '1.4.3', '3c88e10', 'ROLLED_BACK', false, b - 15 * 60e3, 'orders-00015-tor', 8902);

  const i1 = 'inc-demo-001', i2 = 'inc-demo-002';
  const m = (x: number) => x * 60e3;
  const ev1: TimelineEvent[] = [
    canary(a - m(18), r141, 10, 76010),
    verdict(a - m(6), r141, 10, 76012, 'IN_PROGRESS', 0.003, 288, 180),
    verdict(a, r141, 10, 76014, 'FAIL', 0.004, 842, 412, i1, ['p95_ms > 300 (observed 842)']),
    E(a + 4e3, 'incident.detected', SRC.detect, 76014, 'Incident opened for release 1.4.1.', { incident: i1, release: r141.id, sha: r141.commit_sha }),
    E(a + m(1), 'rollback.started', SRC.rollback, 76016, 'Returning 100% of traffic to known-good 1.4.0.', { incident: i1, release: r140.id }),
    E(a + m(2), 'rollback.completed', SRC.rollback, 76017, 'Post-rollback probe healthy on revision orders-00011-kit.', { incident: i1, release: r140.id, evidence: '#probe-76017', data: { verdict: 'PASS', target: 'stable', traffic_percent: 100, error_rate: 0.0009, p95_ms: 34, sample_size: 60, revision_name: 'orders-00011-kit' } }),
    E(a + m(4), 'evidence.collected', SRC.evidence, 76020, 'Redacted evidence bundle sealed (SHA-256 2c26b46b…).', { incident: i1, evidence: '#bundle-001', data: { evidence_sha256: '2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae' } }),
    E(a + m(5), 'flow.started', SRC.flow, 76022, 'Investigation flow started with incident ID and bundle URL only.', { incident: i1 }),
    E(a + m(19), 'flow.completed', SRC.flow, 76022, 'Flow finished: fix proposed.', { incident: i1, data: { outcome: 'fix_proposed' } }),
    E(a + m(19) + 3e3, 'repair.proposed', SRC.flow, 76022, 'Merge request !37 opened on duo/fix/inc-demo-001.', { incident: i1, sha: '5f0a9b3', data: { mr_iid: 37, fix_sha: '5f0a9b3' } }),
    E(a + m(27), 'regression_proof.verdict', SRC.proof, 76031, 'Fails on 9e4d2c7 with AssertionError, passes on 5f0a9b3.', { incident: i1, evidence: '#proof-76031', data: { verdict: 'PASS', fix_sha: '5f0a9b3' } }),
    E(a + m(28), 'integrity_gate.verdict', SRC.integrity, 76032, 'No blocking findings across 9 checks.', { incident: i1, evidence: '#integrity-76032', data: { verdict: 'PASS', findings: [] } }),
    E(a + m(41), 'merge.completed', SRC.merge, 76039, 'All required jobs green on 5f0a9b3. Merged.', { incident: i1, sha: '5f0a9b3', data: { mr_iid: 37, fix_sha: '5f0a9b3' } }),
    canary(a + m(50), r142, 10, 76044, i1),
    verdict(a + m(56), r142, 10, 76046, 'PASS', 0.0011, 39, 402, i1),
    canary(a + m(57), r142, 50, 76047, i1),
    verdict(a + m(63), r142, 50, 76049, 'PASS', 0.001, 38, 1610, i1),
    canary(a + m(64), r142, 100, 76050, i1),
    E(a + m(65), 'redeploy.completed', SRC.deploy, 76050, 'Release 1.4.2 promoted 10% → 50% → 100%.', { incident: i1, release: r142.id, data: { traffic_percent: 100, revision_name: r142.revision_name } }),
    E(a + m(71), 'recovery.verified', SRC.evalr, 76053, 'Release 1.4.2 within thresholds at 100% traffic: error rate 0.10%, p95 37 ms.', { incident: i1, release: r142.id, evidence: '#evaluator-76053', data: { verdict: 'PASS', target: 'candidate', traffic_percent: 100, error_rate: 0.001, p95_ms: 37, sample_size: 3020 } }),
  ];
  const ev2: TimelineEvent[] = [
    canary(b - m(14), r143, 10, 77010),
    verdict(b, r143, 10, 77012, 'FAIL', 0.061, 214, 388, i2, ['error_rate > 0.02 (observed 0.061)']),
    E(b + 4e3, 'incident.detected', SRC.detect, 77012, 'Incident opened for release 1.4.3.', { incident: i2, release: r143.id, sha: r143.commit_sha }),
    E(b + m(1), 'rollback.started', SRC.rollback, 77014, 'Returning 100% of traffic to known-good 1.4.2.', { incident: i2, release: r142.id }),
    E(b + m(2), 'rollback.completed', SRC.rollback, 77015, 'Post-rollback probe healthy on revision orders-00014-ved.', { incident: i2, release: r142.id, evidence: '#probe-77015', data: { verdict: 'PASS', target: 'stable', traffic_percent: 100, error_rate: 0.0011, p95_ms: 36, sample_size: 60, revision_name: 'orders-00014-ved' } }),
    E(b + m(4), 'evidence.collected', SRC.evidence, 77018, 'Redacted evidence bundle sealed (SHA-256 fcde2b2e…).', { incident: i2, evidence: '#bundle-002', data: { evidence_sha256: 'fcde2b2edba56bf408601fb721fe9b5c338d10ee429ea04fae5511b68fbf8fb9' } }),
    E(b + m(5), 'flow.started', SRC.flow, 77020, 'Attempt 1: investigation flow started.', { incident: i2 }),
    E(b + m(22), 'repair.proposed', SRC.flow, 77020, 'Merge request !39 opened on duo/fix/inc-demo-002.', { incident: i2, sha: '1d2e3f4', data: { mr_iid: 39, fix_sha: '1d2e3f4' } }),
    E(b + m(29), 'regression_proof.verdict', SRC.proof, 77027, 'Fails on 3c88e10 with AssertionError, passes on 1d2e3f4.', { incident: i2, evidence: '#proof-77027', data: { verdict: 'PASS', fix_sha: '1d2e3f4' } }),
    E(b + m(30), 'integrity_gate.verdict', SRC.integrity, 77028, 'Blocked: existing test skipped in tests/test_orders.py.', { incident: i2, evidence: '#integrity-77028', data: { verdict: 'FAIL', findings: ['RULE_01_EXISTING_TESTS_MODIFIED', 'RULE_02_TEST_SKIPPED_OR_XFAILED'] } }),
    E(b + m(34), 'flow.started', SRC.flow, 77031, 'Attempt 2: investigation flow started with the gate report attached.', { incident: i2 }),
    E(b + m(55), 'flow.completed', SRC.flow, 77031, 'Flow finished: no fix found. Evidence insufficient to isolate the cause.', { incident: i2, data: { outcome: 'no_fix_found' } }),
  ];

  const d1: IncidentDetail = {
    id: i1, release_id: r141.id, detected_at: iso(a + 4e3), status: 'RECOVERED',
    breached_thresholds: ['p95_ms > 300 (observed 842)'], evidence_bundle_ref: '#bundle-001',
    evidence_sha256: '2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae',
    recovery_attempts: [{
      id: 'att-001-1', attempt_no: 1, state: 'RECOVERED', flow_session_id: 'duo-session-0001', mr_iid: 37, fix_sha: '5f0a9b3',
      analysis: {
        outcome: 'fix_proposed',
        facts: [
          { text: 'Candidate p95 latency was 842 ms against a 300 ms limit; error rate stayed below 1%.', ref: 'evaluator_results.json#L12' },
          { text: 'Candidate logs show one database query per order line in GET /api/v1/orders.', ref: 'cloudrun_candidate_logs.txt#L58' },
          { text: 'Commit 9e4d2c7 replaced a joined query with a per-line lookup in app/routes/orders.py.', ref: 'diff_summary.json#L4' },
        ],
        hypotheses: [{ text: 'An N+1 query introduced by 9e4d2c7 multiplies latency with order size.', confidence: 'high', rationale: 'Latency scales with line count in the sampled requests.' }],
        missing_evidence: [],
        suspected_change: { commit_sha: '9e4d2c7', file_path: 'app/routes/orders.py', line_range: '61-74', reason: 'Per-line lookup inside the request loop.' },
        proposed_fix: 'Restore the joined query and load order lines in one round trip.',
        regression_test_file: 'tests/regressions/test_inc_demo_001.py', expected_failure_type: 'AssertionError',
        file_ref: 'sentinel/incidents/inc-demo-001/analysis.json',
      },
      test_results: [
        { id: 't1', kind: 'regression_on_broken', sha: '9e4d2c7', outcome: 'FAILED', failure_type: 'AssertionError', junit_ref: '#junit-001-b' },
        { id: 't2', kind: 'regression_on_fix', sha: '5f0a9b3', outcome: 'PASSED', junit_ref: '#junit-001-f' },
        { id: 't3', kind: 'suite', sha: '5f0a9b3', outcome: 'PASSED', junit_ref: '#suite-001' },
      ],
      gate_results: [
        { id: 'g1', gate: 'integrity', verdict: 'pass', findings: [], report_ref: '#integrity-76032' },
        { id: 'g2', gate: 'sast', verdict: 'pass', findings: [], report_ref: '#sast-001' },
      ],
    }],
  };
  const d2: IncidentDetail = {
    id: i2, release_id: r143.id, detected_at: iso(b + 4e3), status: 'ESCALATED',
    breached_thresholds: ['error_rate > 0.02 (observed 0.061)'], evidence_bundle_ref: '#bundle-002',
    evidence_sha256: 'fcde2b2edba56bf408601fb721fe9b5c338d10ee429ea04fae5511b68fbf8fb9',
    recovery_attempts: [
      {
        id: 'att-002-1', attempt_no: 1, state: 'FAILED', flow_session_id: 'duo-session-0002', mr_iid: 39, fix_sha: '1d2e3f4',
        failure_reason: 'VERIFICATION_FAILED: the Integrity Gate blocked the merge request because it skipped an existing test.',
        analysis: {
          outcome: 'fix_proposed',
          facts: [
            { text: 'Candidate returned HTTP 500 on POST /api/v1/orders for 6.1% of synthetic requests.', ref: 'evaluator_results.json#L20' },
            { text: 'Errors cluster on orders with a coupon code.', ref: 'cloudrun_candidate_logs.txt#L211' },
          ],
          hypotheses: [
            { text: 'Coupon parsing in 3c88e10 rejects lowercase codes.', confidence: 'medium' },
            { text: 'A cache warm-up race may also contribute.', confidence: 'low' },
          ],
          missing_evidence: ['Coupon codes are redacted in the bundle, so the failing inputs cannot be confirmed.'],
          suspected_change: { commit_sha: '3c88e10', file_path: 'app/services/coupons.py', line_range: '12-30', reason: 'New normalisation step.' },
          proposed_fix: 'Normalise coupon codes before lookup.',
          regression_test_file: 'tests/regressions/test_inc_demo_002.py', expected_failure_type: 'AssertionError',
          file_ref: 'sentinel/incidents/inc-demo-002/analysis.json',
        },
        test_results: [
          { id: 't1', kind: 'regression_on_broken', sha: '3c88e10', outcome: 'FAILED', failure_type: 'AssertionError', junit_ref: '#junit-002-b' },
          { id: 't2', kind: 'regression_on_fix', sha: '1d2e3f4', outcome: 'PASSED', junit_ref: '#junit-002-f' },
        ],
        gate_results: [{
          id: 'g1', gate: 'integrity', verdict: 'fail', report_ref: '#integrity-77028', findings: [
            { rule_id: 'RULE_01_EXISTING_TESTS_MODIFIED', severity: 'BLOCKING', file: 'tests/test_orders.py', message: "Modifying or deleting existing test file 'tests/test_orders.py' (status: M) is strictly prohibited." },
            { rule_id: 'RULE_02_TEST_SKIPPED_OR_XFAILED', severity: 'BLOCKING', file: 'tests/test_orders.py', message: 'Detected addition of pytest skip or xfail marker.' },
          ],
        }],
      },
      {
        id: 'att-002-2', attempt_no: 2, state: 'FAILED', flow_session_id: 'duo-session-0003',
        failure_reason: 'INVESTIGATION_FAILED: the flow returned no_fix_found. Escalated to the on-call engineer.',
        analysis: {
          outcome: 'no_fix_found',
          facts: [{ text: 'The previous repair was blocked by RULE_02_TEST_SKIPPED_OR_XFAILED.', ref: 'integrity_report.json#L9' }],
          hypotheses: [{ text: 'The expired-coupon test encodes behaviour the coupon change broke on purpose; product intent is unclear.', confidence: 'medium' }],
          missing_evidence: ['Unredacted failing coupon inputs.', 'Product decision on expired-coupon handling.'],
          file_ref: 'sentinel/incidents/inc-demo-002/analysis-2.json',
        },
        test_results: [], gate_results: [],
      },
    ],
  };
  return { releases: [r140, r141, r142, r143], r142, d1, d2, ev1, ev2 };
}

/* ---------------- The live scenario ---------------- */
export function demoSnapshot(t0: number, now: number, stepMs: number, fail: boolean): Snapshot & { phase: number } {
  seq = 0;
  const phase = Math.min(PHASES.length - 1, Math.max(0, Math.floor((now - t0) / stepMs)));
  const at = (p: number, extra = 0) => t0 + p * stepMs + 700 + extra;
  const wobble = (a: number) => 1 + a * Math.sin(now / 900) * Math.cos(now / 1700);
  const failed = fail && phase >= 7;
  const ph = failed ? 7 : phase;
  const hist = history(t0);
  const ID = 'inc-demo-003';

  const r150 = R('rel-r-150', '1.5.0', 'd8f23a1', ph >= 2 ? 'ROLLED_BACK' : 'CANARY', false, at(1, -600), 'orders-00016-mir', 9030);
  const r151 = R('rel-r-151', '1.5.1', 'a41be07', ph >= 10 ? 'STABLE' : 'CANARY', ph >= 10, at(9, -600), 'orders-00017-sol', 9062);
  const releases = [...hist.releases, ...(ph >= 1 ? [r150] : []), ...(ph >= 9 && !failed ? [r151] : [])];

  const sched: [number, number, () => TimelineEvent][] = [
    [1, 0, () => canary(at(1), r150, 10, 77530)],
    [1, stepMs * 0.5, () => verdict(at(1, stepMs * 0.5), r150, 10, 77532, 'IN_PROGRESS', 0.019, 122, 240)],
    [2, 0, () => verdict(at(2), r150, 10, 77534, 'FAIL', 0.142, 612, 418, ID, ['error_rate > 0.02 (observed 0.142)', 'p95_ms > 300 (observed 612)'])],
    [2, 80, () => E(at(2, 80), 'incident.detected', SRC.detect, 77534, 'Incident opened for release 1.5.0.', { incident: ID, release: r150.id, sha: r150.commit_sha })],
    [3, -900, () => E(at(3, -900), 'rollback.started', SRC.rollback, 77536, 'Returning 100% of traffic to known-good 1.4.2.', { incident: ID, release: hist.r142.id })],
    [3, 0, () => E(at(3), 'rollback.completed', SRC.rollback, 77537, 'Post-rollback probe healthy on revision orders-00014-ved.', { incident: ID, release: hist.r142.id, evidence: '#probe-77537', data: { verdict: 'PASS', target: 'stable', traffic_percent: 100, error_rate: 0.0011, p95_ms: 38, sample_size: 60, revision_name: 'orders-00014-ved' } })],
    [4, 0, () => E(at(4), 'evidence.collected', SRC.evidence, 77541, 'Redacted evidence bundle sealed (SHA-256 7f83b165…).', { incident: ID, evidence: '#bundle-003', data: { evidence_sha256: '7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069' } })],
    [5, 0, () => E(at(5), 'flow.started', SRC.flow, 77545, 'Investigation flow started with incident ID and bundle URL only.', { incident: ID })],
    [6, -400, () => E(at(6, -400), 'flow.completed', SRC.flow, 77545, 'Flow finished: fix proposed.', { incident: ID, data: { outcome: 'fix_proposed' } })],
    [6, 0, () => E(at(6), 'repair.proposed', SRC.flow, 77545, 'Merge request !42 opened on duo/fix/inc-demo-003.', { incident: ID, sha: 'a41be07', data: { mr_iid: 42, fix_sha: 'a41be07' } })],
    [7, 300, () => E(at(7, 300), 'regression_proof.verdict', SRC.proof, 77552,
      failed ? 'Regression test failed on the broken release with ZeroDivisionError, not an assertion.' : 'Fails on d8f23a1 with AssertionError, passes on a41be07.',
      { incident: ID, evidence: '#proof-77552', data: { verdict: failed ? 'FAIL' : 'PASS', fix_sha: 'a41be07' } })],
    [7, 1200, () => E(at(7, 1200), 'integrity_gate.verdict', SRC.integrity, 77553,
      failed ? 'Blocked: assertion weakened in tests/test_orders.py.' : 'No blocking findings across 9 checks.',
      { incident: ID, evidence: '#integrity-77553', data: { verdict: failed ? 'FAIL' : 'PASS', findings: failed ? ['RULE_04_ASSERT_WEAKENED', 'RULE_01_EXISTING_TESTS_MODIFIED'] : [] } })],
    ...(failed ? [] : ([
      [8, 0, () => E(at(8), 'merge.completed', SRC.merge, 77558, 'All required jobs green on a41be07. Merged.', { incident: ID, sha: 'a41be07', data: { mr_iid: 42, fix_sha: 'a41be07' } })],
      [9, 0, () => canary(at(9), r151, 10, 77562, ID)],
      [9, 900, () => verdict(at(9, 900), r151, 10, 77563, 'PASS', 0.0012, 42, 396, ID)],
      [9, 1300, () => canary(at(9, 1300), r151, 50, 77564, ID)],
      [9, 2100, () => verdict(at(9, 2100), r151, 50, 77565, 'PASS', 0.0011, 40, 1588, ID)],
      [9, 2500, () => canary(at(9, 2500), r151, 100, 77566, ID)],
      [9, 2600, () => E(at(9, 2600), 'redeploy.completed', SRC.deploy, 77566, 'Release 1.5.1 promoted 10% → 50% → 100%.', { incident: ID, release: r151.id, data: { traffic_percent: 100, revision_name: r151.revision_name } })],
      [10, 0, () => E(at(10), 'recovery.verified', SRC.evalr, 77571, 'Release 1.5.1 within thresholds at 100% traffic: error rate 0.10%, p95 41 ms.', { incident: ID, release: r151.id, evidence: '#evaluator-77571', data: { verdict: 'PASS', target: 'candidate', traffic_percent: 100, error_rate: 0.001, p95_ms: 41, sample_size: 3104 } })],
    ] as [number, number, () => TimelineEvent][])),
  ];
  const liveEvents = sched.filter(([p, off]) => ph > p || (ph === p && now >= at(p, off))).map(([, , f]) => f());

  const incStatus = failed ? 'VERIFICATION_FAILED' : ph >= 2 ? PHASES[ph] : null;
  const tests: TestResult[] = [];
  const gates: GateResult[] = [];
  if (ph >= 7 && now >= at(7, 300)) {
    tests.push({ id: 't1', kind: 'regression_on_broken', sha: 'd8f23a1', outcome: 'FAILED', failure_type: failed ? 'ZeroDivisionError' : 'AssertionError', junit_ref: '#junit-003-b' });
    tests.push({ id: 't2', kind: 'regression_on_fix', sha: 'a41be07', outcome: 'PASSED', junit_ref: '#junit-003-f' });
  }
  if (ph >= 7 && now >= at(7, 1200)) {
    gates.push(failed
      ? { id: 'g1', gate: 'integrity', verdict: 'fail', report_ref: '#integrity-77553', findings: [{ rule_id: 'RULE_04_ASSERT_WEAKENED', severity: 'BLOCKING', file: 'tests/test_orders.py', message: 'Assertion equality weakened to truthiness or non-equality check.' }, { rule_id: 'RULE_01_EXISTING_TESTS_MODIFIED', severity: 'BLOCKING', file: 'tests/test_orders.py', message: "Modifying or deleting existing test file 'tests/test_orders.py' (status: M) is strictly prohibited." }] }
      : { id: 'g1', gate: 'integrity', verdict: 'pass', findings: [], report_ref: '#integrity-77553' });
  }
  if (!failed && ph >= 7 && now >= at(7, 2400)) {
    gates.push({ id: 'g2', gate: 'sast', verdict: 'pass', findings: [], report_ref: '#sast-003' });
    tests.push({ id: 't3', kind: 'suite', sha: 'a41be07', outcome: 'PASSED', junit_ref: '#suite-003' });
  }

  const live: IncidentDetail | null = incStatus ? {
    id: ID, release_id: r150.id, detected_at: iso(at(2, 80)), status: incStatus,
    breached_thresholds: ['error_rate > 0.02 (observed 0.142)', 'p95_ms > 300 (observed 612)'],
    evidence_bundle_ref: ph >= 4 ? '#bundle-003' : undefined,
    evidence_sha256: ph >= 4 ? '7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069' : undefined,
    recovery_attempts: ph >= 5 ? [{
      id: 'att-003-1', attempt_no: 1, state: failed ? 'FAILED' : PHASES[ph], flow_session_id: 'duo-session-0004',
      mr_iid: ph >= 6 ? 42 : undefined, fix_sha: ph >= 6 ? 'a41be07' : undefined,
      failure_reason: failed ? 'VERIFICATION_FAILED: the regression test failed for the wrong reason and the Integrity Gate blocked a weakened assertion.' : undefined,
      analysis: ph >= 6 || (ph === 5 && now >= at(5, stepMs * 0.5)) ? {
        outcome: ph >= 6 ? 'fix_proposed' : undefined,
        facts: [
          { text: 'Candidate returned HTTP 500 on POST /api/v1/orders for 14.2% of synthetic requests; stable returned none.', ref: 'evaluator_results.json#L18' },
          { text: 'Candidate logs show ZeroDivisionError in app/routes/orders.py, calculate_discount.', ref: 'cloudrun_candidate_logs.txt#L104' },
          { text: 'The only change to calculate_discount between 1.4.2 and 1.5.0 is commit d8f23a1.', ref: 'diff_summary.json#L7' },
        ],
        hypotheses: [
          { text: 'The refactor divides by an item count that evaluates to zero for every order.', confidence: 'high', rationale: 'Every failing request hits the same line.' },
          { text: 'Premium-tier orders may also round incorrectly after the change.', confidence: 'low' },
        ],
        missing_evidence: ['Per-tier error breakdown during the canary window was not captured in the bundle.'],
        suspected_change: { commit_sha: 'd8f23a1', file_path: 'app/routes/orders.py', line_range: '38-46', reason: 'Adds an unchecked division in the discount path.' },
        proposed_fix: ph >= 6 ? 'Remove the zero divisor and compute the tier discount directly from the subtotal.' : undefined,
        regression_test_file: ph >= 6 ? 'tests/regressions/test_inc_demo_003.py' : undefined,
        expected_failure_type: ph >= 6 ? 'AssertionError' : undefined,
        file_ref: 'sentinel/incidents/inc-demo-003/analysis.json',
      } : undefined,
      test_results: tests,
      gate_results: gates,
    }] : [],
  } : null;

  const err = ph === 1 ? 0.019 : ph === 2 ? 0.142 : ph === 9 ? 0.0012 : ph >= 3 ? 0.0011 : 0.0012;
  const p95 = ph === 1 ? 122 : ph === 2 ? 612 : ph >= 3 ? 38 : 36;
  const pct9 = now >= at(9, 2500) ? 100 : now >= at(9, 1300) ? 50 : 10;
  const status: SystemStatus = {
    current_release: ph >= 10 && !failed ? r151 : hist.r142,
    candidate_release: ph === 1 || ph === 2 ? r150 : ph === 9 && !failed ? r151 : null,
    traffic_split: ph === 1 || ph === 2 ? { stable_percent: 90, candidate_percent: 10 }
      : ph === 9 && !failed ? { stable_percent: 100 - pct9, candidate_percent: pct9 }
      : { stable_percent: 100, candidate_percent: 0 },
    system_health: { error_rate: err * wobble(0.08), p95_ms: p95 * wobble(0.06), healthy: ph !== 2 },
    active_incident: live && live.status !== 'RECOVERED' ? { ...live } : null,
  };

  const details: Record<string, IncidentDetail> = { [hist.d1.id]: hist.d1, [hist.d2.id]: hist.d2 };
  const timelines: Record<string, TimelineEvent[]> = { [hist.d1.id]: hist.ev1.filter((e) => e.incident_id), [hist.d2.id]: hist.ev2.filter((e) => e.incident_id) };
  if (live) { details[ID] = live; timelines[ID] = liveEvents.filter((e) => e.incident_id === ID); }
  const strip = ({ recovery_attempts: _r, ...i }: IncidentDetail) => i;
  const incidents = [live, hist.d2, hist.d1].filter((x): x is IncidentDetail => !!x).map(strip);
  const events = [...hist.ev1, ...hist.ev2, ...liveEvents].sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  const focus = live ?? hist.d2;

  return {
    phase: ph, status, releases, incidents, details, timelines, events,
    healthz: { status: 'ok', service: 'sentinel-backend (demo)', version: 'demo' },
    focus, timeline: timelines[focus.id] ?? [],
  };
}
