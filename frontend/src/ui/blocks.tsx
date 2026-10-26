/** Larger pieces shared by the overview and the incident page: stages, AI analysis, proof, outcome. */
import { GITLAB_URL } from '../api/client';
import type { GateFinding, GateResult, RecoveryAttempt, TestResult, TimelineEvent } from '../api/types';
import { FAILURE_COPY, isFailure, readProof, type StageView } from '../state/derive';
import { Badge, Empty, STATE_WORD, time, type Tone } from './kit';

/** The rules sentinel/scripts/integrity_gate.py enforces. Every one is blocking. Examples are illustrative. */
export const RULES = [
  { id: 'RULE_01', name: 'Existing tests intact', what: 'Editing or deleting an existing file under tests/. Only new files in tests/regressions/ are allowed.', ex: 'M  tests/test_orders.py' },
  { id: 'RULE_02', name: 'No skip or xfail', what: 'Adding a pytest skip or xfail marker to get a failing test out of the way.', ex: '+ @pytest.mark.skip(reason="flaky")' },
  { id: 'RULE_03', name: 'No assertions removed', what: 'Deleting an assertion without replacing it.', ex: '- assert total == 90' },
  { id: 'RULE_04', name: 'No assertions weakened', what: 'Turning an equality check into a truthiness or inequality check.', ex: '- assert total == 90\n+ assert total' },
  { id: 'RULE_05', name: 'CI and test config intact', what: 'Touching .gitlab-ci.yml, conftest.py, pytest.ini, pyproject.toml or setup.cfg.', ex: 'M  .gitlab-ci.yml' },
  { id: 'RULE_06', name: 'Test count preserved', what: 'Deleting a test function.', ex: '- def test_discount_for_gold():' },
  { id: 'RULE_07', name: 'No harness escapes', what: 'Exiting the process, or behaving differently when PYTEST_CURRENT_TEST is set.', ex: '+ if os.environ.get("PYTEST_CURRENT_TEST"):' },
  { id: 'RULE_08', name: 'No expectation changes', what: 'Changing the expected value in a test instead of fixing the code.', ex: '- assert total == 90\n+ assert total == 100' },
  { id: 'RULE_09', name: 'No always-true __eq__', what: 'Overriding __eq__ to return True so every comparison passes.', ex: '+ def __eq__(self, o): return True' },
] as const;

export const GATE_NAME: Record<string, string> = { integrity: 'Integrity Gate', holdout: 'Hidden holdout gate', sast: 'Static analysis', sonar: 'Sonar quality gate', terraform: 'Terraform validate' };

export function gateWord(g?: GateResult): [Tone, string] {
  if (!g) return ['mute', 'pending'];
  return g.verdict === 'pass' ? ['ok', 'pass'] : g.verdict === 'fail' ? ['bad', 'blocked'] : g.verdict === 'warn' ? ['warn', 'warn'] : ['mute', g.verdict || 'unknown'];
}
function testWord(t?: TestResult): [Tone, string] {
  if (!t) return ['mute', 'pending'];
  return t.outcome === 'PASSED' ? ['ok', 'pass'] : ['bad', t.outcome === 'ERROR' ? 'error' : 'fail'];
}
const findingText = (f?: GateFinding) => (f ? `${f.rule_id ? `${f.rule_id}: ` : ''}${f.message}` : undefined);

/** Every stage with who decides it and the event that backs it. */
export function StageList({ stages }: { stages: StageView[] }) {
  const tone: Record<string, Tone> = { sourced: 'ok', unsourced: 'ok', confirmed: 'ok', advisory: 'ai', active: 'warn', failed: 'bad' };
  return (
    <ol className="stages">
      {stages.map((s) => (
        <li key={s.stage}>
          <span className="n">{String(s.n).padStart(2, '0')}</span>
          <div><b style={{ fontWeight: 500 }}>{s.label}</b><span className="who" style={{ display: 'block' }}>{s.authority}</span></div>
          <div className="what">
            {s.event ? <>{s.event.summary ?? s.event.type} <span className="muted small">· {time(s.event.at)}{s.event.job && ` · job ${s.event.job}`}</span></>
              : <span className="muted">{s.state === 'blocked' ? 'Not reached: an earlier stage failed.' : s.state === 'waiting' ? '—' : 'No source event recorded.'}</span>}
          </div>
          <Badge tone={tone[s.state] ?? 'mute'}>{STATE_WORD[s.state]}</Badge>
        </li>
      ))}
    </ol>
  );
}

/** What the Duo flow read, suspected and proposed. Advisory only. */
export function Analysis({ attempt, hasIncident }: { attempt?: RecoveryAttempt; hasIncident: boolean }) {
  const a = attempt?.analysis;
  const mr = attempt?.mr_iid;
  const sc = a?.suspected_change;
  if (!a) return <Empty title={hasIncident ? 'The AI has not written an analysis yet.' : 'No investigation running.'}><span className="muted small">When an incident reaches investigation, the flow's facts and hypotheses appear here, kept apart from proof.</span></Empty>;
  return (
    <div className="stack">
      {a.outcome === 'no_fix_found' && <div className="note note--warn"><b>No fix found.</b> The flow declined to propose a repair. Sentinel does not guess; this goes to a person.</div>}
      <div className="grid g2">
        <div className="card ai-card">
          <span className="label">Cited observations — each with the evidence it refers to</span>
          {a.facts.length ? <ul className="ai-list">{a.facts.map((f, i) => <li key={i}>{f.text}{f.ref ? <code className="ref">{f.ref}</code> : <span className="ref is-none">no reference given</span>}</li>)}</ul> : <p className="muted">None recorded.</p>}
        </div>
        <div className="card ai-card">
          <span className="label">Hypotheses — guesses, not facts</span>
          {a.hypotheses.length ? <ul className="ai-list">{a.hypotheses.map((h, i) => <li key={i}>{h.text}{h.rationale && <span className="ref" style={{ fontFamily: 'var(--sans)' }}>{h.rationale}</span>}{h.confidence && <span className="ref">self-rated confidence: {h.confidence}</span>}</li>)}</ul> : <p className="muted">None recorded.</p>}
          {a.missing_evidence.length > 0 && <><span className="label" style={{ marginTop: 14 }}>Evidence it did not have</span><ul className="ai-list">{a.missing_evidence.map((m, i) => <li key={i}>{m}</li>)}</ul></>}
        </div>
      </div>
      {(sc || a.proposed_fix) && (
        <div className="card">
          <dl className="kv">
            {sc && <><dt>Suspected change</dt><dd className="mono">{sc.raw ?? <>{sc.file_path ?? 'unknown file'}{sc.line_range && `:${sc.line_range}`}{sc.commit_sha && ` in ${sc.commit_sha}`}{sc.reason && ` — ${sc.reason}`}</>}</dd></>}
            {a.proposed_fix && <><dt>Proposed repair</dt><dd>{a.proposed_fix}</dd></>}
            {a.regression_test_file && <><dt>Regression test</dt><dd><code>{a.regression_test_file}</code>{a.expected_failure_type && <span className="muted"> · must fail with {a.expected_failure_type} on the broken release</span>}</dd></>}
            <dt>Merge request</dt>
            <dd>{mr !== undefined ? (GITLAB_URL ? <a href={`${GITLAB_URL}/-/merge_requests/${mr}`} target="_blank" rel="noreferrer">!{mr} ↗</a> : `!${mr}`) : <span className="muted">none recorded</span>}{attempt?.fix_sha && <span className="muted"> · fix commit <code>{attempt.fix_sha}</code></span>}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}

/** The deterministic verdicts for one recovery attempt. */
export function Proof({ attempt }: { attempt?: RecoveryAttempt }) {
  const p = readProof(attempt);
  const gates = attempt?.gate_results ?? [];
  const integrity = gates.find((g) => g.gate === 'integrity');
  const reg: [Tone, string] = p.verdict === 'proven' ? ['ok', 'proven'] : p.verdict === 'rejected' ? ['bad', 'rejected'] : p.verdict === 'partial' ? ['warn', 'partial'] : ['mute', 'pending'];
  const tiles: { name: string; v: [Tone, string]; note: string; link?: string }[] = [
    { name: 'Regression proof', v: reg, note: p.reason },
    { name: 'Integrity Gate', v: gateWord(integrity), note: findingText(integrity?.findings[0]) ?? (integrity ? 'No blocking findings.' : 'No result recorded yet.'), link: integrity?.report_ref },
    ...(attempt?.holdout_gate ? [{ name: 'Hidden holdout gate', v: (attempt.holdout_gate.verdict === 'PASS' ? ['ok', 'verified'] : ['bad', 'violated']) as [Tone, string], note: `${attempt.holdout_gate.invariants_passed}/${attempt.holdout_gate.invariants_tested} secret invariants held in the gate container.` }] : []),
    { name: 'Full test suite', v: testWord(p.suite), note: p.suite ? `On ${p.suite.sha}` : 'No result recorded yet.', link: p.suite?.junit_ref },
    ...gates.filter((g) => g.gate !== 'integrity').map((g) => ({ name: GATE_NAME[g.gate] ?? g.gate, v: gateWord(g), note: findingText(g.findings[0]) ?? 'No blocking findings.', link: g.report_ref })),
  ];
  return (
    <>
      <div className="grid g3">
        {tiles.map((t) => (
          <div key={t.name} className="card">
            <div className="verdict"><h3>{t.name}</h3><Badge tone={t.v[0]}>{t.v[1]}</Badge></div>
            <p className="small" style={{ color: 'var(--ink-2)' }}>{t.note}</p>
            {t.link && <a className="small" href={t.link} target="_blank" rel="noreferrer">report ↗</a>}
          </div>
        ))}
      </div>
      {(p.broken || p.fix) && (
        <div className="runs">
          <div className={`run ${p.broken?.outcome === 'FAILED' && /assert/i.test(p.broken.failure_type ?? '') ? 'is-good' : p.broken ? 'is-bad' : ''}`}>
            <span className="label">On the broken release {p.broken && <code>{p.broken.sha}</code>}</span>
            <p>Must fail with an assertion. Got <b>{p.broken ? `${p.broken.outcome}${p.broken.failure_type ? ` · ${p.broken.failure_type}` : ''}` : 'not run yet'}</b>.</p>
          </div>
          <div className={`run ${p.fix?.outcome === 'PASSED' ? 'is-good' : p.fix ? 'is-bad' : ''}`}>
            <span className="label">On the fix {p.fix && <code>{p.fix.sha}</code>}</span>
            <p>Must pass. Got <b>{p.fix ? p.fix.outcome : 'not run yet'}</b>.</p>
          </div>
        </div>
      )}
    </>
  );
}

export function Outcome({ status, attempt, verified }: { status: string | null; attempt?: RecoveryAttempt; verified?: TimelineEvent }) {
  const state = !status ? 'none' : status === 'RECOVERED' ? 'confirmed' : isFailure(status) ? 'stopped' : 'pending';
  const word = { none: 'ALL CLEAR', confirmed: 'RECOVERED', stopped: 'STOPPED', pending: 'NOT YET' }[state];
  return (
    <div className={`card outcome outcome--${state}`}>
      <span className="outcome__word">{word}</span>
      <p>
        {state === 'confirmed' && (verified ? <>{verified.summary ?? 'Recovery verified by the post-redeploy evaluator.'} <span className="muted small">· <code>{verified.source}</code>{verified.job && ` job ${verified.job}`} · {time(verified.at)}</span></> : 'The incident record says RECOVERED.')}
        {state === 'stopped' && status && <>{FAILURE_COPY[status] ?? status}. {attempt?.failure_reason} Sentinel stopped rather than ship an unproven fix.</>}
        {state === 'pending' && 'Recovery is confirmed only when the evaluator checks the redeployed release at full traffic. Never by the AI, never by this page.'}
        {state === 'none' && 'No incident recorded.'}
      </p>
    </div>
  );
}

/** Candidate fixes and the deterministic trust score, when the attempt carries them. */
export function Candidates({ attempt }: { attempt?: RecoveryAttempt }) {
  const t = attempt?.trust_score, c = attempt?.candidates ?? [];
  if (!t && !c.length) return <Empty title="No candidate fixes or trust score recorded for this attempt." />;
  return (
    <div className="stack">
      {t && (
        <div className="card">
          <div className="verdict"><h3>Trust score {t.trust_score} / {t.max_score}</h3><Badge tone={t.trust_score >= 70 ? 'ok' : t.trust_score >= 40 ? 'warn' : 'bad'}>{t.rating}</Badge></div>
          <p className="small" style={{ color: 'var(--ink-2)' }}>{t.recommendation}</p>
          <ul className="ai-list" style={{ marginTop: 10 }}>
            {[...t.deductions.map((d) => ({ ...d, s: '−' })), ...t.bonuses.map((b) => ({ ...b, s: '+' }))].map((x, i) => <li key={i}><b style={{ fontWeight: 500 }}>{x.s}{Math.abs(x.points)} {x.factor}</b><span className="ref" style={{ fontFamily: 'var(--sans)' }}>{x.reason}</span></li>)}
          </ul>
          <p className="small muted" style={{ marginTop: 8 }}>{t.governance_rule}</p>
        </div>
      )}
      {c.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Candidate</th><th>Status</th><th className="num">Trust</th><th>Gates</th></tr></thead>
            <tbody>{c.map((x) => (
              <tr key={x.candidate_id}>
                <td>{x.title}<span className="sub">{x.approach}</span></td>
                <td><Badge tone={x.status === 'SELECTED' ? 'ok' : 'bad'}>{x.status.toLowerCase()}</Badge>{x.rejection_reason && <span className="sub">{x.rejection_reason}</span>}</td>
                <td className="num">{x.trust_score}</td>
                <td className="small mono">integrity {x.gate_results.integrity_gate} · holdout {x.gate_results.holdout_gate} · proof {x.gate_results.regression_proof}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
