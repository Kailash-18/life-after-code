import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { GITLAB_URL } from '../api/client';
import { useIncident, useSentinel } from '../api/source';
import { AI, Loop, Outcome, Proof } from '../sections/Sections';
import { MODE_COLOR, viewIncident } from '../state/derive';
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
  const events = timeline ?? [];
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
  const sealed = events.find((e) => e.type === 'evidence.collected');
  const verified = events.find((e) => e.type === 'recovery.verified');
  const allFindings = att?.gate_results.flatMap((g) => g.findings.map((f) => ({ ...f, gate: g.gate }))) ?? [];
  const branch = `duo/fix/${id}`;
  // The backend may leave detected_at empty; the recorded incident.detected event is the next-best source.
  const detectedAt = base.detected_at || events.find((e) => e.type === 'incident.detected')?.at || '';

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

      <section className="sec sec--tight" id="repair">
        <SecHead num="04" title="The repair">What the flow opened. A merge request is a proposal: it merges only when every required job passes.</SecHead>
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

      <Proof attempt={att} num="05" id="proof" />

      {allFindings.length > 0 && (
        <section className="sec sec--tight" id="findings">
          <SecHead num="06" title="Why it was blocked">Every finding the gates reported for this attempt, verbatim.</SecHead>
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

      <Outcome status={base.status} attempt={att} verified={verified} num="07" id="outcome" />

      <section className="sec sec--tight" id="timeline">
        <SecHead num="08" title="Timeline">Every event recorded for {id}, oldest first.</SecHead>
        {events.length ? <EventList events={events} now={now} /> : <Empty title="No events recorded for this incident." />}
      </section>
    </div>
  );
}
