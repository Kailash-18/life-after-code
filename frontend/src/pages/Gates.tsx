import { Link } from 'react-router-dom';
import { useSentinel } from '../api/source';
import type { GateFinding } from '../api/types';
import { readProof } from '../state/derive';
import { useMission } from '../state/mission';
import { GATE_NAME, RULES, gateWord } from '../ui/blocks';
import { Badge, Empty, EventList, PageHead, Section } from '../ui/kit';

export default function Gates() {
  const { snap } = useSentinel();
  const { now } = useMission();
  const attempts = Object.values(snap.details).flatMap((d) => d.recovery_attempts.map((a) => ({ inc: d.id, a })));
  const findings: (GateFinding & { inc: string; attempt: number })[] = attempts.flatMap(({ inc, a }) => a.gate_results.flatMap((g) => g.findings.map((f) => ({ ...f, inc, attempt: a.attempt_no }))));
  const hits = (id: string) => findings.filter((f) => f.rule_id?.startsWith(id)).length;
  const proofs = attempts.map(({ inc, a }) => ({ inc, a, p: readProof(a) })).filter((x) => x.p.verdict !== 'pending');
  const results = attempts.flatMap(({ inc, a }) => a.gate_results.map((g) => ({ inc, a, g })));
  const gateEvents = snap.events.filter((e) => ['integrity_gate.verdict', 'regression_proof.verdict', 'merge.completed'].includes(e.type));

  return (
    <>
      <PageHead eyebrow="Gates" title="A repair merges only if it proves itself">
        Two CI jobs, outside the AI's control, decide whether an AI-written fix can merge: the regression proof and the Integrity Gate. Then every required job must pass.
      </PageHead>

      <Section title="Regression proof" note="One new test, run twice. Both conditions must hold.">
        <div className="law">
          <div className="card tilt"><span className="k">1 · broken release</span><h3 style={{ marginTop: 6 }}>The test must fail with an assertion</h3><p>A crash such as ImportError is not proof the test catches the bug.</p></div>
          <div className="card tilt"><span className="k">2 · the fix</span><h3 style={{ marginTop: 6 }}>The same test must pass</h3><p>Run against the commit the AI proposed.</p></div>
          <div className="card tilt"><span className="k">= verdict</span><h3 style={{ marginTop: 6 }}>Proven, or rejected</h3><p>Anything other than both is rejected and the repair cannot merge.</p></div>
        </div>
        {proofs.length > 0 && (
          <div className="table-wrap" style={{ marginTop: 14 }}>
            <table>
              <thead><tr><th>Incident</th><th>Verdict</th><th>Reason</th></tr></thead>
              <tbody>{proofs.map(({ inc, a, p }) => (
                <tr key={`${inc}-${a.attempt_no}`}>
                  <td><Link to={`/incidents/${encodeURIComponent(inc)}`}>{inc}</Link><span className="sub">attempt {a.attempt_no}</span></td>
                  <td><Badge tone={p.verdict === 'proven' ? 'ok' : p.verdict === 'rejected' ? 'bad' : 'warn'}>{p.verdict}</Badge></td>
                  <td className="small">{p.reason}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Integrity Gate · 9 rules" note="Reads the repair's diff and blocks any way of making tests pass without fixing the code. Every rule is blocking.">
        <div className="rules">
          {RULES.map((r) => {
            const n = hits(r.id);
            return (
              <div key={r.id} className="rule">
                <span className="id">{r.id}</span>
                <div><b>{r.name}</b><p>{r.what}</p></div>
                <pre>{r.ex}</pre>
                <span className={`hits${n ? ' is-hit' : ''}`}>{n ? `${n} caught` : '—'}</span>
              </div>
            );
          })}
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>Examples are illustrative. A clean report means none of these patterns were found; whether the fix is correct is the regression proof's job.</p>
      </Section>

      <Section title="Recorded verdicts" note="Every gate result attached to a recovery attempt.">
        {results.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Incident</th><th>Gate</th><th>Verdict</th><th>Findings</th><th /></tr></thead>
              <tbody>{results.map(({ inc, a, g }) => {
                const [tone, word] = gateWord(g);
                return (
                  <tr key={`${inc}-${a.attempt_no}-${g.id}`}>
                    <td><Link to={`/incidents/${encodeURIComponent(inc)}`}>{inc}</Link><span className="sub">attempt {a.attempt_no}</span></td>
                    <td>{GATE_NAME[g.gate] ?? g.gate}</td>
                    <td><Badge tone={tone}>{word}</Badge></td>
                    <td className="small mono">{g.findings.length ? g.findings.map((f) => f.rule_id ?? f.message).join(', ') : <span className="muted">none</span>}</td>
                    <td className="small">{g.report_ref && <a href={g.report_ref} target="_blank" rel="noreferrer">report ↗</a>}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        ) : <Empty title="No gate results recorded yet." />}
      </Section>

      {findings.length > 0 && (
        <Section title="What the gates caught" note="Verbatim.">
          <div className="rules">
            {findings.map((f, i) => (
              <div key={i} className="rule" style={{ gridTemplateColumns: '110px minmax(0,1fr) auto' }}>
                <span className="id">{f.rule_id ?? 'finding'}</span>
                <div><p style={{ color: 'var(--ink)' }}>{f.message}</p>{f.file && <code className="small muted">{f.file}</code>}</div>
                <Link className="small" to={`/incidents/${encodeURIComponent(f.inc)}`}>{f.inc}</Link>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="Gate events" note="The raw events the gate jobs sent.">
        {gateEvents.length ? <EventList events={gateEvents.slice().reverse()} showIncident now={now} /> : <Empty title="No gate events recorded yet." />}
      </Section>
    </>
  );
}
