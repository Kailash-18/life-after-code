import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSentinel } from '../api/source';
import type { Release, TimelineEvent } from '../api/types';
import { accepted } from '../state/derive';
import { useMission } from '../state/mission';
import { Badge, Empty, Metric, PageHead, Readouts, Section, Sha, ago, dateTime, dur, ms, num, pct, time, type Tone } from '../ui/kit';

const verdictOf = (e: TimelineEvent) => (typeof e.data?.verdict === 'string' ? e.data.verdict : undefined);
const relTone = (s: string): Tone => (s === 'ROLLED_BACK' ? 'bad' : s === 'STABLE' || s === 'PROMOTED' ? 'ok' : s === 'CANARY' ? 'warn' : 'mute');

function Ladder({ rel, events }: { rel: Release; events: TimelineEvent[] }) {
  const mine = events.filter((e) => e.release_id === rel.id && ['deploy.canary_started', 'evaluator.verdict', 'recovery.verified'].includes(e.type));
  const steps = mine.filter((e) => e.type === 'deploy.canary_started').map((c, i, all) => {
    const next = all[i + 1];
    const within = mine.filter((e) => e.type !== 'deploy.canary_started' && Date.parse(e.at) >= Date.parse(c.at) && (!next || Date.parse(e.at) < Date.parse(next.at)));
    const final = [...within].reverse().find((e) => verdictOf(e) !== 'IN_PROGRESS') ?? within[within.length - 1];
    return { c, pct: num(c.data?.traffic_percent), v: final };
  });
  if (!steps.length) return <Empty title={`No canary steps recorded for ${rel.version}.`}><span className="muted small">Steps appear from recorded deploy.canary_started and evaluator.verdict events.</span></Empty>;
  return (
    <div className="ladder">
      {steps.map(({ c, pct: p, v }) => {
        const vv = v ? verdictOf(v) : undefined;
        return (
          <div key={c.id} className={`card rung${vv === 'FAIL' ? ' rung--fail' : ''}`}>
            <div className="verdict"><span className="pct">{p ?? '?'}<small>%</small></span><Badge tone={vv === 'PASS' ? 'ok' : vv === 'FAIL' ? 'bad' : 'mute'}>{vv ?? 'no verdict'}</Badge></div>
            <div className="rung__bar"><span style={{ width: `${p ?? 0}%` }} /></div>
            <span className="label">of traffic on {rel.version}</span>
            {v ? <Readouts e={v} /> : <p className="small muted">No verdict recorded for this step.</p>}
            <p className="small muted" style={{ marginTop: 8 }}>{time(c.at)}{c.job && ` · job ${c.job}`}</p>
          </div>
        );
      })}
      {rel.status === 'ROLLED_BACK' && (
        <div className="card rung rung--fail">
          <div className="verdict"><span className="pct">0<small>%</small></span><Badge tone="bad">rolled back</Badge></div>
          <p className="small" style={{ color: 'var(--ink-2)' }}>Traffic returned to the last known-good release.</p>
        </div>
      )}
    </div>
  );
}

export default function Rollout() {
  const { snap } = useSentinel();
  const { now } = useMission();
  const st = snap.status;
  const releases = useMemo(() => snap.releases ?? [], [snap.releases]);
  const byId = useMemo(() => new Map(releases.map((r) => [r.id, r])), [releases]);
  const evs = accepted(snap.events);
  const defaultRel = st?.candidate_release?.id ?? [...releases].reverse().find((r) => evs.some((e) => e.release_id === r.id && e.type === 'deploy.canary_started'))?.id ?? releases[releases.length - 1]?.id;
  const [pick, setPick] = useState<string | null>(null);
  const sel = byId.get(pick ?? defaultRel ?? '') ?? null;
  const split = st?.traffic_split ?? null;
  const verdicts = evs.filter((e) => e.type === 'evaluator.verdict' || e.type === 'recovery.verified').slice().reverse();
  const rollbacks = evs.filter((e) => e.type === 'rollback.started').map((s) => ({
    s, done: evs.find((e) => e.type === 'rollback.completed' && e.incident_id === s.incident_id && Date.parse(e.at) >= Date.parse(s.at)),
  })).reverse();
  const knownGood = [...releases].reverse().find((r) => r.known_good);

  return (
    <>
      <PageHead eyebrow="Releases" title="What went to production, and what the evaluator said">
        Every release goes out as a canary: a small share of traffic first, checked by the health evaluator at each step. Traffic moves only through the deploy jobs; this page only reads.
      </PageHead>

      <div className="grid g4">
        <div className="card tilt"><Metric value={st?.current_release?.version ?? '—'} label="Serving" /></div>
        <div className="card tilt"><Metric value={st?.candidate_release?.version ?? '—'} label="Candidate on trial" /></div>
        <div className="card tilt"><Metric value={split ? `${split.candidate_percent}%` : '—'} label="Traffic on the candidate" /></div>
        <div className="card tilt"><Metric value={knownGood?.version ?? '—'} label="Last known good" /></div>
      </div>

      <Section title="Releases" note="Newest first. Select one to see its canary steps.">
        {releases.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Version</th><th>Status</th><th>Commit</th><th>Revision</th><th>Pipeline</th><th className="num">Created</th></tr></thead>
              <tbody>
                {[...releases].reverse().map((r) => (
                  <tr key={r.id} className={`is-link${sel?.id === r.id ? ' is-sel' : ''}`} onClick={() => setPick(r.id)}>
                    <td><b style={{ fontWeight: 500 }}>{r.version}</b>
                      <span className="sub">{st?.current_release?.id === r.id ? 'serving' : st?.candidate_release?.id === r.id ? 'candidate' : r.known_good ? 'known good' : ' '}</span></td>
                    <td><Badge tone={relTone(r.status)}>{r.status.replace(/_/g, ' ').toLowerCase()}</Badge></td>
                    <td className="mono small">{r.commit_sha ? r.commit_sha.slice(0, 12) : '—'}</td>
                    <td className="mono small">{r.revision_name ?? '—'}</td>
                    <td className="mono small">{r.pipeline_id ?? '—'}</td>
                    <td className="num small">{ago(r.created_at, now)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty title="The API has not returned any releases." />}
      </Section>

      {sel && (
        <Section title={`Canary steps · ${sel.version}`} note="10% → 50% → 100%, each step checked by the evaluator. A failing step ends in a rollback.">
          <div className="row" style={{ marginBottom: 14 }}>
            <Sha label="commit" value={sel.commit_sha || undefined} />
            <Sha label="image" value={sel.image_digest} />
            <span className="small muted">created {dateTime(sel.created_at)}</span>
          </div>
          <Ladder rel={sel} events={evs} />
        </Section>
      )}

      <Section title="Evaluator verdicts" note="Newest first. These are the evaluator's own measurements.">
        {verdicts.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>When</th><th>Release</th><th>Verdict</th><th className="num">Traffic</th><th className="num">Errors</th><th className="num">p95</th><th className="num">Samples</th><th>Breached</th></tr></thead>
              <tbody>
                {verdicts.map((e) => {
                  const v = verdictOf(e) ?? '—';
                  const br = Array.isArray(e.data?.breached_thresholds) ? (e.data.breached_thresholds as string[]) : [];
                  const er = num(e.data?.error_rate), p = num(e.data?.p95_ms), n = num(e.data?.sample_size), tp = num(e.data?.traffic_percent);
                  return (
                    <tr key={e.id}>
                      <td className="small">{dateTime(e.at)}<span className="sub">job {e.job ?? '—'}</span></td>
                      <td>{e.release_id ? byId.get(e.release_id)?.version ?? e.release_id : '—'}</td>
                      <td><Badge tone={v === 'PASS' ? 'ok' : v === 'FAIL' ? 'bad' : 'mute'}>{e.type === 'recovery.verified' ? 'recovered' : v.toLowerCase()}</Badge></td>
                      <td className="num">{tp !== undefined ? `${tp}%` : '—'}</td>
                      <td className="num">{er !== undefined ? pct(er) : '—'}</td>
                      <td className="num">{p !== undefined ? ms(p) : '—'}</td>
                      <td className="num">{n ?? '—'}</td>
                      <td className="small" style={{ color: br.length ? 'var(--bad)' : undefined }}>{br.length ? br.join('; ') : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <Empty title="No evaluator verdicts recorded yet." />}
      </Section>

      <Section title="Rollbacks" note="Containment counts only when a probe confirms the old release is healthy again.">
        {rollbacks.length ? (
          <div className="grid g2">
            {rollbacks.map(({ s, done }) => (
              <div key={s.id} className="card">
                <div className="verdict">
                  <h3>→ {s.release_id ? byId.get(s.release_id)?.version ?? 'known good' : 'known good'}</h3>
                  <Badge tone={done ? 'ok' : 'warn'}>{done ? 'probe healthy' : 'no probe yet'}</Badge>
                </div>
                <p className="small" style={{ color: 'var(--ink-2)' }}>{s.summary}</p>
                {done && <><Readouts e={done} /><p className="small muted" style={{ marginTop: 6 }}>confirmed {dur(s.at, done.at)} after it started</p></>}
                {s.incident_id && <Link className="small" to={`/incidents/${encodeURIComponent(s.incident_id)}`}>{s.incident_id} →</Link>}
              </div>
            ))}
          </div>
        ) : <Empty title="No rollbacks recorded." />}
      </Section>
    </>
  );
}
