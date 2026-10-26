import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSentinel } from '../api/source';
import { buildStages, isFailure } from '../state/derive';
import { useMission } from '../state/mission';
import { Badge, Empty, Metric, Mini, PageHead, ago, dateTime, dur, spanMs, statusTone, statusWord } from '../ui/kit';

type Filter = 'all' | 'open' | 'recovered' | 'stopped';
const FILTERS: [Filter, string][] = [['all', 'All'], ['open', 'Open'], ['recovered', 'Recovered'], ['stopped', 'Stopped']];

export default function Incidents() {
  const { snap } = useSentinel();
  const { d, now } = useMission();
  const nav = useNavigate();
  const [f, setF] = useState<Filter>('all');
  const all = snap.incidents ?? [];
  const cls = (s: string): Filter => (s === 'RECOVERED' ? 'recovered' : isFailure(s) ? 'stopped' : 'open');
  const list = all.filter((i) => f === 'all' || cls(i.status) === f);
  const count = (k: Filter) => all.filter((i) => k === 'all' || cls(i.status) === k).length;
  const ttr = all.map((i) => {
    const v = snap.timelines[i.id]?.find((e) => !e.rejected && e.type === 'recovery.verified');
    return v ? Date.parse(v.at) - Date.parse(i.detected_at) : NaN;
  }).filter(Number.isFinite).sort((a, b) => a - b);
  const median = ttr.length ? ttr[Math.floor(ttr.length / 2)] : null;

  return (
    <>
      <PageHead eyebrow="Incidents" title="Every regression Sentinel caught">
        Each incident is one trip around the loop. Open one to see the evidence, the AI's proposal, the gate verdicts and how it ended.
      </PageHead>

      <div className="grid g4" style={{ marginBottom: 28 }}>
        <div className="card tilt"><Metric value={count('all')} label="Recorded" /></div>
        <div className="card tilt"><Metric value={count('recovered')} label="Recovered" tone={count('recovered') ? 'ok' : undefined} /></div>
        <div className="card tilt"><Metric value={count('stopped')} label="Stopped or escalated" /></div>
        <div className="card tilt"><Metric value={median === null ? '—' : spanMs(median)} label="Median time to verified recovery" /></div>
      </div>

      <div className="filters">
        <div className="seg" role="group" aria-label="Filter incidents">
          {FILTERS.map(([k, l]) => <button key={k} className={f === k ? 'is-on' : ''} onClick={() => setF(k)} aria-pressed={f === k}>{l}<small>{count(k)}</small></button>)}
        </div>
      </div>

      {snap.incidents === null ? <Empty title="Waiting for the incident list." /> : !list.length ? (
        <Empty title={all.length ? 'No incidents match this filter.' : 'No incidents recorded.'}><span className="muted small">{all.length ? 'Pick another filter.' : 'The first regression the evaluator catches will appear here.'}</span></Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Incident</th><th>Status</th><th>Release</th><th>Breached</th><th>Progress</th><th className="num">Duration</th></tr></thead>
            <tbody>
              {list.map((i) => {
                const tl = snap.timelines[i.id] ?? [];
                const rel = snap.releases?.find((r) => r.id === i.release_id);
                const live = d.incidentActive && d.incident?.id === i.id;
                const done = tl.find((e) => !e.rejected && e.type === 'recovery.verified');
                const go = () => nav(`/incidents/${encodeURIComponent(i.id)}`);
                return (
                  <tr key={i.id} className="is-link" onClick={go}>
                    <td><a href={`#/incidents/${encodeURIComponent(i.id)}`} onClick={(e) => { e.preventDefault(); go(); }} style={{ fontWeight: 500 }}>{i.id}</a><span className="sub">{dateTime(i.detected_at)} · {ago(i.detected_at, now)}</span></td>
                    <td><Badge tone={statusTone(i.status)}>{statusWord(i.status)}</Badge>{live && <span className="sub">live</span>}</td>
                    <td>{rel?.version ?? i.release_id}{rel?.commit_sha && <span className="sub mono">{rel.commit_sha.slice(0, 8)}</span>}</td>
                    <td className="small">{i.breached_thresholds.length ? i.breached_thresholds.join('; ') : <span className="muted">none reported</span>}</td>
                    <td><Mini stages={buildStages(i.status, tl)} /></td>
                    <td className="num small">{done ? dur(i.detected_at, done.at) : isFailure(i.status) ? '—' : dur(i.detected_at, new Date(now).toISOString())}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
