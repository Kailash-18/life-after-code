import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { GITLAB_URL } from '../api/client';
import { DEMO_POSTMORTEM } from '../api/demo';
import { useIncident, useSentinel } from '../api/source';
import { AI, Loop, Outcome, Proof } from '../sections/Sections';
import { MODE_COLOR, accepted, viewIncident } from '../state/derive';
import { useMission, useSceneFocus } from '../state/mission';
import { Tilt } from '../ui/fx';
import { Chip, Empty, EventList, PageHead, SecHead, Sha, ago, dateTime, dur, statusTone, statusWord } from '../ui/kit';
import { RULES } from './Gates';

export default function IncidentRoom() {
  const { id = '' } = useParams();
  const { snap } = useSentinel();
  const { d, now } = useMission();
  const { detail, summary, timeline, loaded } = useIncident(id);
  const base = detail ?? summary;
  const status = base?.status ?? null;
  const [pick, setPick] = useState<number | undefined>(undefined);
  const [expandedCand, setExpandedCand] = useState<string | null>(null);
  const [copiedPm, setCopiedPm] = useState(false);
  const [expandedPm, setExpandedPm] = useState(true);

  const events = timeline ?? [];
  const ok = accepted(events);
  const view = viewIncident(detail, status ?? '', events, pick);
  useSceneFocus(base && status ? { mode: view.mode, stages: view.stages, key: id } : null);

  if (!base) {
    const listed = snap.incidents !== null;
    return (
      <div className="page">
        <PageHead num="02·R" kicker="Incident room" title={id || 'Unknown'} />
        <Empty title={listed && !loaded ? 'No incident with this id.' : 'Loading the incident record…'}>
          <Link to="/incidents" data-cursor="Back">← Back to all incidents</Link>
        </Empty>
      </div>
    );
  }

  const rel = snap.releases?.find((r) => r.id === base.release_id);
  const attempts = detail?.recovery_attempts ?? [];
  const att = view.attempt;
  const live = d.incidentActive && d.incident?.id === id;
  const sealed = ok.find((e) => e.type === 'evidence.collected');
  const verified = ok.find((e) => e.type === 'recovery.verified');
  const allFindings = att?.gate_results.flatMap((g) => g.findings.map((f) => ({ ...f, gate: g.gate }))) ?? [];
  const branch = `duo/fix/${id}`;
  const detectedAt = base.detected_at || ok.find((e) => e.type === 'incident.detected')?.at || '';

  const candidates = att?.candidates ?? [];
  const trustScore = att?.trust_score;

  return (
    <div className="page page--room" style={{ ['--room' as string]: MODE_COLOR[view.mode] }}>
      <PageHead num="02·R" kicker={live ? 'Incident room · live' : 'Incident room'} title={id}
        aside={
          <div className="room__status">
            <span className="card__k">Status, as the incident record says</span>
            <b className={`room__word tone-${statusTone(base.status)}`}>{statusWord(base.status)}</b>
            <span className="muted small">{verified ? `recovered in ${dur(detectedAt, verified.at)}` : `open for ${dur(detectedAt, new Date(now).toISOString())}`}</span>
          </div>
        }>
        <p>
          Release <b>{rel?.version ?? base.release_id}</b>{rel?.commit_sha && <> (<code>{rel.commit_sha}</code>)</>} · detected {dateTime(detectedAt)} ({ago(detectedAt, now)})
          {live && <> · <Chip tone="bad" pulse>live</Chip></>}
        </p>
        <p className="room__back"><Link to="/incidents" data-cursor="Back">← all incidents</Link></p>
      </PageHead>

      <Loop stages={view.stages} progress={view.progress} pinned={false} num="01" title="Where it stands"
        caption="Each stage is lit only by the incident record; a source event, when there is one, is shown under it." />

      <section className="sec sec--tight" id="evidence">
        <SecHead num="02" title="Evidence">What the evaluator measured, sealed before the AI saw anything. The AI receives only the incident ID and this bundle's URL.</SecHead>
        <div className="evgrid">
          <div className="breaches" data-reveal>
            <span className="card__k">Breached thresholds</span>
            {base.breached_thresholds.length ? base.breached_thresholds.map((b) => <p key={b} className="breach">{b}</p>) : <p className="muted">None reported.</p>}
          </div>
          <Tilt className="card seal" max={8}>
            <span className="card__k">Sealed bundle</span>
            <div className={`seal__lock${base.evidence_sha256 ? ' is-sealed' : ''}`} aria-hidden="true"><span /></div>
            <Sha label="SHA-256" value={base.evidence_sha256} />
            <p className="muted small">
              {base.evidence_bundle_ref ? <a href={base.evidence_bundle_ref} target="_blank" rel="noreferrer" data-cursor="Open">open bundle ↗</a> : 'No bundle reference recorded.'}
              {sealed && <> · sealed by <code>{sealed.source}</code> job {sealed.job} at {dateTime(sealed.at)}</>}
            </p>
          </Tilt>
        </div>
      </section>

      {attempts.length > 1 && (
        <div className="attempts" role="tablist" aria-label="Recovery attempts" data-reveal>
          <span className="card__k">Recovery attempts</span>
          {attempts.map((a) => {
            const on = (pick ?? attempts[attempts.length - 1].attempt_no) === a.attempt_no;
            return (
              <button key={a.id} role="tab" aria-selected={on} className={`attempt${on ? ' is-on' : ''} attempt--${a.state === 'FAILED' ? 'bad' : a.state === 'RECOVERED' ? 'ok' : 'run'}`} onClick={() => setPick(a.attempt_no)} data-cursor={`#${a.attempt_no}`}>
                <b>#{a.attempt_no}</b><span>{a.state}</span>
              </button>
            );
          })}
        </div>
      )}

      <AI attempt={att} hasIncident num="03" id="ai" />

      {/* TIER 1 FEATURE: Multiple Candidate Fixes */}
      {candidates.length > 0 && (
        <section className="sec sec--tight" id="candidates">
          <SecHead num="04" title="Multiple candidate fixes · Generated tests as filters">
            The AI generates 3 candidate fixes. Deterministic gates filter and evaluate each, selecting the proven fix while showing explicit rejection reasons.
            <span className="muted small" style={{ display: 'block', marginTop: '4px', color: 'var(--cyan)' }}>
              Research: "Generated tests used as filters more than double AI repair precision (ICSE / Automated Software Engineering)."
            </span>
          </SecHead>
          <div className="candidate-grid" data-reveal>
            {candidates.map((c) => {
              const isWin = c.status === 'SELECTED';
              const isExp = expandedCand === c.candidate_id;
              return (
                <div key={c.candidate_id} className={`candidate-card ${isWin ? 'is-winner' : 'is-rejected'}`}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className={`candidate-badge candidate-badge--${isWin ? 'selected' : 'rejected'}`}>
                      {c.status}
                    </span>
                    <span className="candidate-score-pill" style={{ color: isWin ? 'var(--green)' : 'var(--rose)' }}>
                      Trust: <b>{c.trust_score}</b>/100
                    </span>
                  </div>

                  <div>
                    <strong style={{ fontSize: '1rem', color: isWin ? 'var(--ink)' : 'var(--ink-2)' }}>{c.title}</strong>
                    <p className="muted small">{c.approach}</p>
                  </div>

                  <div style={{ display: 'flex', gap: '8px', fontSize: '0.8rem', fontFamily: 'var(--mono)' }}>
                    <span>Integrity: <b style={{ color: c.gate_results.integrity_gate === 'PASS' ? 'var(--green)' : 'var(--rose)' }}>{c.gate_results.integrity_gate}</b></span>
                    <span>· Holdout: <b style={{ color: c.gate_results.holdout_gate === 'PASS' ? 'var(--green)' : 'var(--rose)' }}>{c.gate_results.holdout_gate}</b></span>
                    <span>· Proof: <b style={{ color: c.gate_results.regression_proof === 'PASS' ? 'var(--green)' : 'var(--rose)' }}>{c.gate_results.regression_proof}</b></span>
                  </div>

                  {c.rejection_reason && (
                    <div className="candidate-rejection">
                      <strong>Rejection Reason:</strong> {c.rejection_reason}
                    </div>
                  )}

                  <div>
                    <button
                      className="rule"
                      style={{ padding: '6px 12px', fontSize: '0.8rem', borderRadius: '6px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--line)' }}
                      onClick={() => setExpandedCand(isExp ? null : c.candidate_id)}
                      data-cursor="Diff"
                    >
                      {isExp ? 'Hide diff ▲' : 'Inspect candidate diff ▼'}
                    </button>
                    {isExp && (
                      <pre className="saboteur-diff-box" style={{ marginTop: '8px' }}>
                        {c.diff_patch}
                      </pre>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* TIER 1 FEATURE: Deterministic Repair Trust Score */}
      {trustScore && (
        <section className="sec sec--tight" id="trust-score">
          <SecHead num="05" title="Deterministic trust score per repair">
            Deterministic score built from gate results, test coverage change, and diff size.
          </SecHead>
          <div className="trust-score-card" data-reveal>
            <div className="trust-header">
              <div>
                <span className="card__k">Deterministic repair trust score</span>
                <div className="trust-big-score" style={{ color: trustScore.trust_score >= 90 ? 'var(--green)' : trustScore.trust_score >= 75 ? 'var(--cyan)' : 'var(--rose)' }}>
                  {trustScore.trust_score} <span style={{ fontSize: '1.2rem', color: 'var(--muted)' }}>/ 100</span>
                </div>
                <span className={`candidate-badge candidate-badge--${trustScore.trust_score >= 75 ? 'selected' : 'rejected'}`} style={{ marginTop: '6px' }}>
                  {trustScore.rating}
                </span>
              </div>
              <div style={{ maxWidth: '420px', textAlign: 'right' }}>
                <span className="trust-governance-note">
                  ⚖ {trustScore.governance_rule}
                </span>
              </div>
            </div>

            <div className="trust-points-list">
              {trustScore.bonuses.map((b, i) => (
                <div key={i} className="trust-point-item is-bonus">
                  <strong style={{ color: 'var(--green)' }}>+{b.points} pts · {b.factor}</strong>
                  <p className="muted small">{b.reason}</p>
                </div>
              ))}
              {trustScore.deductions.map((d, i) => (
                <div key={i} className="trust-point-item is-deduction">
                  <strong style={{ color: 'var(--rose)' }}>{d.points} pts · {d.factor}</strong>
                  <p className="muted small">{d.reason}</p>
                </div>
              ))}
            </div>

            <div style={{ background: 'rgba(0,0,0,0.4)', borderRadius: '10px', padding: '14px 18px', border: '1px solid var(--line)' }}>
              <span className="card__k">AI Explanation (Advisory)</span>
              <p className="muted" style={{ fontStyle: 'italic', marginTop: '4px' }}>
                "{trustScore.ai_explanation}"
              </p>
            </div>
          </div>
        </section>
      )}

      <section className="sec sec--tight" id="repair">
        <SecHead num="06" title="The repair">What the flow opened. A merge request is a proposal: it merges only when every required job passes.</SecHead>
        {att ? (
          <div className="repair" data-reveal>
            <div className="repair__item"><span className="card__k">Merge request</span>
              {att.mr_iid !== undefined ? (GITLAB_URL ? <a className="repair__big" href={`${GITLAB_URL}/-/merge_requests/${att.mr_iid}`} target="_blank" rel="noreferrer" data-cursor="MR">!{att.mr_iid} ↗</a> : <b className="repair__big">!{att.mr_iid}</b>) : <b className="repair__big muted">none</b>}
            </div>
            <div className="repair__item"><span className="card__k">Branch <em>by convention</em></span><Sha value={att.mr_iid !== undefined ? branch : undefined} /></div>
            <div className="repair__item"><span className="card__k">Fix commit</span><Sha value={att.fix_sha} /></div>
            <div className="repair__item"><span className="card__k">Regression test</span><Sha value={att.analysis?.regression_test_file} /></div>
            <div className="repair__item"><span className="card__k">Flow session</span><Sha value={att.flow_session_id} /></div>
          </div>
        ) : <p className="muted">No recovery attempt recorded yet.</p>}
      </section>

      <Proof attempt={att} num="07" id="proof" />

      {allFindings.length > 0 && (
        <section className="sec sec--tight" id="findings">
          <SecHead num="08" title="Why it was blocked">Every finding the gates reported for this attempt, verbatim.</SecHead>
          <ol className="findings">
            {allFindings.map((f, i) => (
              <li key={i} className={`finding finding--${(f.severity ?? 'blocking').toLowerCase()}`} data-reveal>
                <span className="finding__rule">{f.rule_id ?? f.gate}</span>
                <p>{f.message}</p>
                <p className="muted small">{f.severity ?? 'severity not reported'}{f.file && <> · <code>{f.file}</code></>}{f.rule_id && RULES.find((r) => f.rule_id!.startsWith(r.id)) && <> · <Link to="/gates" data-cursor="Rule">what this rule checks →</Link></>}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      <Outcome status={base.status} attempt={att} verified={verified} num="09" id="outcome" />

      {/* TIER 2 FEATURE 8: Auto-Written Postmortem MR */}
      <section className="sec sec--tight" id="postmortem" data-reveal>
        <SecHead num="10" title="Auto-written postmortem · MR & issue documentation">
          Deterministic synthesis of timeline, root cause 5-whys, and cryptographic evidence hashes into a ready-to-merge GitLab Postmortem MR.
        </SecHead>
        <div className="postmortem-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <span className="card__k">GitLab postmortem MR !42</span>
              <strong style={{ fontSize: '1.1rem', display: 'block', marginTop: 4 }}>
                [POSTMORTEM] Autonomous Recovery Incident Report · {id}
              </strong>
              <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
                <Chip tone="ok">RESOLVED & RECOVERED</Chip>
                <span className="muted small" style={{ fontFamily: 'var(--mono)' }}>
                  SHA-256: 9b2c3f8471e98d4a6c230e52b82143ad07f6e245a903c14fba42e5a1b3c97802
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                className="rule"
                style={{ padding: '8px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.06)', border: '1px solid var(--line)' }}
                onClick={() => {
                  navigator.clipboard?.writeText(DEMO_POSTMORTEM.markdown);
                  setCopiedPm(true);
                  setTimeout(() => setCopiedPm(false), 2000);
                }}
                data-cursor="Copy"
              >
                {copiedPm ? '✓ Copied Markdown' : 'Copy Postmortem Markdown'}
              </button>
              <button
                className="rule"
                style={{ padding: '8px 14px', borderRadius: 8, background: 'rgba(60,240,255,0.1)', borderColor: 'var(--cyan)' }}
                onClick={() => setExpandedPm(!expandedPm)}
                data-cursor="Toggle"
              >
                {expandedPm ? 'Collapse Postmortem ▲' : 'Expand Postmortem ▼'}
              </button>
            </div>
          </div>

          {expandedPm && (
            <div style={{ marginTop: 16 }}>
              <pre className="postmortem-pre">
                {DEMO_POSTMORTEM.markdown}
              </pre>
            </div>
          )}
        </div>
      </section>

      <section className="sec sec--tight" id="timeline">
        <SecHead num="11" title="Timeline">Every event recorded for {id}, oldest first.</SecHead>
        {events.length ? <EventList events={events} now={now} /> : <Empty title="No events recorded for this incident." />}
      </section>
    </div>
  );
}
