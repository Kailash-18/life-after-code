import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useSentinel } from '../api/source';
import type { GateFinding } from '../api/types';
import { GATE_NAME, gateStamp } from '../sections/Sections';
import { readProof } from '../state/derive';
import { useMission } from '../state/mission';
import { Tilt } from '../ui/fx';
import { EventList, PageHead, SecHead } from '../ui/kit';

/** The rules sentinel/scripts/integrity_gate.py enforces. Every one is BLOCKING. Examples are illustrative. */
export const RULES = [
  { id: 'RULE_01', name: 'Existing tests intact', what: 'Any edit or deletion of an existing file under tests/. Only new files in tests/regressions/ are allowed.', ex: 'M  tests/test_orders.py' },
  { id: 'RULE_02', name: 'No skip or xfail', what: 'Adding a pytest skip or xfail marker to get a red test out of the way.', ex: '+ @pytest.mark.skip(reason="flaky")' },
  { id: 'RULE_03', name: 'No assertions removed', what: 'Deleting an assertion without replacing it.', ex: '- assert total == 90' },
  { id: 'RULE_04', name: 'No assertions weakened', what: 'Turning an equality check into a truthiness or non-equality check.', ex: '- assert total == 90\n+ assert total' },
  { id: 'RULE_05', name: 'CI and test config intact', what: 'Touching .gitlab-ci.yml, conftest.py, pytest.ini, pyproject.toml or setup.cfg.', ex: 'M  .gitlab-ci.yml' },
  { id: 'RULE_06', name: 'Test count preserved', what: 'Deleting a test function definition.', ex: '- def test_discount_for_gold():' },
  { id: 'RULE_07', name: 'No harness escapes', what: 'Exiting the process or branching on PYTEST_CURRENT_TEST to behave differently under test.', ex: '+ if os.environ.get("PYTEST_CURRENT_TEST"):' },
  { id: 'RULE_08', name: 'No expectation mutation', what: 'Changing the expected value in a test instead of fixing the application.', ex: '- assert total == 90\n+ assert total == 100' },
  { id: 'RULE_09', name: 'No always-true __eq__', what: 'Overriding __eq__ to return True so every comparison passes.', ex: '+ def __eq__(self, o): return True' },
] as const;

function RuleCard({ r, hits }: { r: (typeof RULES)[number]; hits: number }) {
  const [flip, setFlip] = useState(false);
  return (
    <li data-reveal>
      <button className={`rule${flip ? ' is-flip' : ''}${hits ? ' has-hits' : ''}`} onClick={() => setFlip((x) => !x)} data-cursor={flip ? 'Back' : 'Flip'} aria-pressed={flip}>
        <span className="rule__inner">
          <span className="rule__face rule__front">
            <span className="rule__id">{r.id}</span>
            <span className="rule__name">{r.name}</span>
            <span className="rule__sev">BLOCKING</span>
            <span className="rule__hits"><b>{hits}</b> {hits === 1 ? 'time' : 'times'} triggered in recorded results</span>
          </span>
          <span className="rule__face rule__back">
            <span className="rule__id">{r.id}</span>
            <span className="rule__what">{r.what}</span>
            <code className="rule__ex">{r.ex}</code>
            <span className="muted small">example of what it catches</span>
          </span>
        </span>
      </button>
    </li>
  );
}

export default function Gates() {
  const { snap } = useSentinel();
  const { now } = useMission();
  const attempts = Object.values(snap.details).flatMap((d) => d.recovery_attempts.map((a) => ({ inc: d.id, a })));
  const findings: (GateFinding & { inc: string; attempt: number })[] = attempts.flatMap(({ inc, a }) => a.gate_results.flatMap((g) => g.findings.map((f) => ({ ...f, inc, attempt: a.attempt_no }))));
  const hits = (id: string) => findings.filter((f) => f.rule_id?.startsWith(id)).length;
  const results = attempts.flatMap(({ inc, a }) => a.gate_results.map((g) => ({ inc, a, g })));
  const proofs = attempts.map(({ inc, a }) => ({ inc, a, p: readProof(a) })).filter((x) => x.p.verdict !== 'pending');
  const gateEvents = snap.events.filter((e) => e.type === 'integrity_gate.verdict' || e.type === 'regression_proof.verdict' || e.type === 'merge.completed');

  return (
    <div className="page">
      <PageHead num="03" kicker="Gates · deterministic, outside the AI's control" title="Gates">
        <p>An AI-written repair merges only if it proves itself. Two jobs decide: the regression proof and the Integrity Gate. Then every required CI job must pass. The AI cannot change any of them.</p>
      </PageHead>

      <section className="sec sec--tight">
        <SecHead num="A" title="Regression proof">One new test, run twice. Both conditions must hold.</SecHead>
        <div className="prooflaw" data-reveal>
          <div className="law law--broken"><span className="law__n">1</span><b>On the broken release</b><p>the new test must <strong>fail with an assertion</strong>. A crash (ZeroDivisionError, ImportError…) is not proof the test catches the bug.</p></div>
          <div className="law law--fix"><span className="law__n">2</span><b>On the fix</b><p>the same test must <strong>pass</strong>.</p></div>
          <div className="law law--then"><span className="law__n">=</span><b>PROVEN</b><p>Anything else is <strong>REJECTED</strong>, and the repair cannot merge.</p></div>
        </div>
        {proofs.length > 0 && (
          <ol className="gatelog" data-reveal>
            {proofs.map(({ inc, a, p }) => (
              <li key={`${inc}-${a.attempt_no}`} className={`gl gl--${p.verdict === 'proven' ? 'pass' : p.verdict === 'rejected' ? 'fail' : 'warn'}`}>
                <span className="gl__v">{p.verdict.toUpperCase()}</span>
                <Link to={`/incidents/${encodeURIComponent(inc)}`} data-cursor="Room">{inc} · attempt {a.attempt_no}</Link>
                <span className="muted small">{p.reason}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="sec sec--tight">
        <SecHead num="B" title="Integrity Gate · 9 rules">Reads the repair's diff and blocks any attempt to make tests pass without fixing the code. Flip a card to see what it catches.</SecHead>
        <ol className="rules">{RULES.map((r) => <RuleCard key={r.id} r={r} hits={hits(r.id)} />)}</ol>
        <p className="muted small gates__note">A clean report means none of these patterns were found in the diff. It is not a claim that the repair is correct — that is the regression proof's job.</p>
      </section>

      <section className="sec sec--tight">
        <SecHead num="C" title="Recorded verdicts">Every gate result attached to a recovery attempt.</SecHead>
        {results.length ? (
          <ol className="gatelog" data-reveal>
            {results.map(({ inc, a, g }) => {
              const [tone, word] = gateStamp(g);
              return (
                <li key={`${inc}-${a.attempt_no}-${g.id}`} className={`gl gl--${tone}`}>
                  <span className="gl__v">{word}</span>
                  <span className="gl__g">{GATE_NAME[g.gate] ?? g.gate}</span>
                  <Link to={`/incidents/${encodeURIComponent(inc)}`} data-cursor="Room">{inc} · attempt {a.attempt_no}</Link>
                  <span className="muted small">{g.findings.length ? g.findings.map((f) => f.rule_id ?? f.message).join(', ') : 'no findings'}</span>
                  {g.report_ref && <a href={g.report_ref} target="_blank" rel="noreferrer" data-cursor="Report">report ↗</a>}
                </li>
              );
            })}
          </ol>
        ) : <p className="muted">No gate results recorded yet.</p>}
      </section>

      {findings.length > 0 && (
        <section className="sec sec--tight">
          <SecHead num="D" title="Findings">What the gates actually caught, verbatim.</SecHead>
          <div className="findgrid">
            {findings.map((f, i) => (
              <Tilt key={i} className="card finding finding--blocking" max={8}>
                <span className="finding__rule">{f.rule_id ?? 'finding'}</span>
                <p>{f.message}</p>
                <p className="muted small">{f.severity ?? 'severity not reported'}{f.file && <> · <code>{f.file}</code></>} · <Link to={`/incidents/${encodeURIComponent(f.inc)}`}>{f.inc} #{f.attempt}</Link></p>
              </Tilt>
            ))}
          </div>
        </section>
      )}

      <section className="sec sec--tight">
        <SecHead num="E" title="Gate events">The raw events the gate jobs sent.</SecHead>
        {gateEvents.length ? <EventList events={gateEvents.slice().reverse()} showIncident now={now} /> : <p className="muted">No gate events recorded yet.</p>}
      </section>
    </div>
  );
}
