import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { GITLAB_URL } from '../api/client';
import { useIncident, useSentinel } from '../api/source';
import { accepted, viewIncident } from '../state/derive';
import { useMission } from '../state/mission';
import { Analysis, Candidates, Outcome, Proof, RULES, StageList } from '../ui/blocks';
import { Badge, Empty, EventList, PageHead, Section, Sha, Track, ago, dateTime, dur, statusTone, statusWord } from '../ui/kit';

export default function IncidentRoom() {
  const { id = '' } = useParams();
  const { snap } = useSentinel();
  const { d, now } = useMission();
  const { detail, summary, timeline, loaded } = useIncident(id);
  const base = detail ?? summary;
  const [pick, setPick] = useState<number | undefined>(undefined);
  const events = timeline ?? [];
  const ok = accepted(events);
  const view = viewIncident(detail, base?.status ?? '', events, pick);

  if (!base) {
    return (
      <>
        <Link to="/incidents" className="back">← All incidents</Link>
        <PageHead eyebrow="Incident" title={id || 'Unknown'} />
        <Empty title={snap.incidents !== null && !loaded ? 'No incident with this id.' : 'Loading the incident record…'} />
      </>
    );
  }

  const rel = snap.releases?.find((r) => r.id === base.release_id);
  const attempts = detail?.recovery_attempts ?? [];
  const att = view.attempt;
  const live = d.incidentActive && d.incident?.id === id;
  const sealed = ok.find((e) => e.type === 'evidence.collected');
  const verified = ok.find((e) => e.type === 'recovery.verified');
  const findings = att?.gate_results.flatMap((g) => g.findings.map((f) => ({ ...f, gate: g.gate }))) ?? [];
  const detectedAt = base.detected_at || ok.find((e) => e.type === 'incident.detected')?.at || '';

  return (
    <>
      <Link to="/incidents" className="back">← All incidents</Link>
      <PageHead eyebrow={live ? 'Incident · live' : 'Incident'} title={id}
        aside={
          <div style={{ textAlign: 'right' }}>
            <Badge tone={statusTone(base.status)}>{statusWord(base.status)}</Badge>
            <p className="small muted" style={{ marginTop: 6 }}>{verified ? `Recovered in ${dur(detectedAt, verified.at)}` : `Open for ${dur(detectedAt, new Date(now).toISOString())}`}</p>
          </div>
        }>
        Release <b>{rel?.version ?? base.release_id}</b>{rel?.commit_sha && <> (<code>{rel.commit_sha.slice(0, 12)}</code>)</>}, detected {dateTime(detectedAt)} ({ago(detectedAt, now)}).
      </PageHead>

      <div className="card"><Track stages={view.stages} /></div>

      <Section title="Evidence" note="Measured and sealed before the AI saw anything.">
        <div className="grid g2">
          <div className="card">
            <span className="label">Breached thresholds</span>
            {base.breached_thresholds.length ? <ul className="stack">{base.breached_thresholds.map((b) => <li key={b} className="mono" style={{ color: 'var(--bad)' }}>{b}</li>)}</ul> : <p className="muted">None reported.</p>}
          </div>
          <div className="card">
            <span className="label">Sealed bundle</span>
            <Sha label="SHA-256" value={base.evidence_sha256} />
            <p className="small muted" style={{ marginTop: 8 }}>
              {base.evidence_bundle_ref ? <a href={base.evidence_bundle_ref} target="_blank" rel="noreferrer">Open bundle ↗</a> : 'No bundle reference recorded.'}
              {sealed && <> · sealed by <code>{sealed.source}</code>{sealed.job && ` job ${sealed.job}`} at {dateTime(sealed.at)}</>}
            </p>
          </div>
        </div>
      </Section>

      {attempts.length > 1 && (
        <div className="filters" style={{ marginTop: 32 }}>
          <span className="small muted">Recovery attempt</span>
          <div className="seg" role="tablist">
            {attempts.map((a) => {
              const on = (pick ?? attempts[attempts.length - 1].attempt_no) === a.attempt_no;
              return <button key={a.id} role="tab" aria-selected={on} className={on ? 'is-on' : ''} onClick={() => setPick(a.attempt_no)}>#{a.attempt_no}<small>{a.state.toLowerCase()}</small></button>;
            })}
          </div>
        </div>
      )}

      <Section title="AI analysis" note="Written by the GitLab Duo flow. Advisory only — nothing here counts as proof.">
        <Analysis attempt={att} hasIncident />
      </Section>

      <Section title="The repair" note="A merge request is a proposal. It merges only when every required job passes.">
        {att ? (
          <div className="card">
            <dl className="kv">
              <dt>Merge request</dt><dd>{att.mr_iid !== undefined ? (GITLAB_URL ? <a href={`${GITLAB_URL}/-/merge_requests/${att.mr_iid}`} target="_blank" rel="noreferrer">!{att.mr_iid} ↗</a> : `!${att.mr_iid}`) : <span className="muted">none</span>}</dd>
              <dt>Branch</dt><dd><Sha value={att.mr_iid !== undefined ? `duo/fix/${id}` : undefined} /></dd>
              <dt>Fix commit</dt><dd><Sha value={att.fix_sha} /></dd>
              <dt>Regression test</dt><dd><Sha value={att.analysis?.regression_test_file} /></dd>
              <dt>Flow session</dt><dd><Sha value={att.flow_session_id} /></dd>
            </dl>
          </div>
        ) : <Empty title="No recovery attempt recorded yet." />}
      </Section>

      <Section title="Gate verdicts" note="Deterministic jobs the AI cannot change. Only these can let a repair merge.">
        <Proof attempt={att} />
        {findings.length > 0 && (
          <div className="rules" style={{ marginTop: 14 }}>
            {findings.map((f, i) => (
              <div key={i} className="rule" style={{ gridTemplateColumns: '110px minmax(0,1fr) auto' }}>
                <span className="id">{f.rule_id ?? f.gate}</span>
                <div><p style={{ color: 'var(--ink)' }}>{f.message}</p>{f.file && <code className="small muted">{f.file}</code>}</div>
                {f.rule_id && RULES.some((r) => f.rule_id!.startsWith(r.id)) ? <Link className="small" to="/gates">rule ↗</Link> : <span />}
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Candidates and trust score" note="Deterministic score from gate results; the AI can explain it but never set it.">
        <Candidates attempt={att} />
      </Section>

      <Section title="Outcome">
        <Outcome status={base.status} attempt={att} verified={verified} />
      </Section>

      <Section title="Stages" note="Who decides each stage, and the event that backs it.">
        <StageList stages={view.stages} />
      </Section>

      <Section title="Timeline" note={`Every event recorded for ${id}, oldest first.`}>
        {events.length ? <EventList events={events} now={now} /> : <Empty title="No events recorded for this incident." />}
      </Section>
    </>
  );
}
