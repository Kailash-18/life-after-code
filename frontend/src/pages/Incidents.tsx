import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useSentinel } from '../api/source';
import { buildStages, isFailure } from '../state/derive';
import { useMission } from '../state/mission';
import { Count, Tilt } from '../ui/fx';
import { Chip, Empty, MiniLoop, PageHead, ago, dateTime, dur, spanMs, statusTone, statusWord } from '../ui/kit';

type Filter = 'all' | 'open' | 'recovered' | 'stopped';

export default function Incidents() {
  const { snap } = useSentinel();
  const { d, now } = useMission();
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
    <div className="page">
      <PageHead num="02" kicker="Incidents · every regression Sentinel caught" title="Incidents">
        <p>Each incident is one trip around the loop. Open one to see its evidence, the AI's proposal, the gates' verdicts and how it ended.</p>
      </PageHead>

      <div className="stats" data-reveal>
        {([['all', 'Recorded'], ['open', 'Open'], ['recovered', 'Recovered'], ['stopped', 'Stopped']] as [Filter, string][]).map(([k, l]) => (
          <button key={k} className={`stat stat--${k}${f === k ? ' is-on' : ''}`} onClick={() => setF(k)} data-cursor="Filter" aria-pressed={f === k}>
            <b><Count value={count(k)} format={(v) => String(Math.round(v))} /></b><span>{l}</span>
          </button>
        ))}
        <div className="stat stat--ttr">
          <b>{median === null ? '—' : spanMs(median)}</b>
          <span>median detect → verified recovery</span>
        </div>
      </div>

      <section className="sec sec--tight">
        {snap.incidents === null ? <Empty title="Waiting for the incident list." /> : !list.length ? (
          <Empty title={all.length ? 'No incidents match this filter.' : 'No incidents recorded.'}>{all.length ? 'Pick another filter above.' : 'The loop is armed. The first regression the evaluator catches will appear here.'}</Empty>
        ) : (
          <ol className="inclist">
            {list.map((i, n) => {
              const det = snap.details[i.id];
              const tl = snap.timelines[i.id] ?? [];
              const stages = buildStages(i.status, tl);
              const rel = snap.releases?.find((r) => r.id === i.release_id);
              const live = d.incidentActive && d.incident?.id === i.id;
              const recovered = tl.find((e) => !e.rejected && e.type === 'recovery.verified');
              return (
                <li key={i.id} data-reveal style={{ ['--i' as string]: n }}>
                  <Link to={`/incidents/${encodeURIComponent(i.id)}`} className="inc-link" data-cursor="Enter">
                    <Tilt className={`card inc inc--${statusTone(i.status)}${live ? ' is-live' : ''}`} max={8}>
                      <div className="inc__top">
                        <Chip tone={statusTone(i.status)} pulse={live}>{statusWord(i.status)}</Chip>
                        {live && <span className="inc__live">LIVE</span>}
                        <span className="muted small">{dateTime(i.detected_at)} · {ago(i.detected_at, now)}</span>
                      </div>
                      <h3 className="inc__id">{i.id}</h3>
                      <p className="inc__rel">release <b>{rel?.version ?? i.release_id}</b>{rel?.commit_sha && <> · <code>{rel.commit_sha}</code></>}</p>
                      <ul className="inc__br">{i.breached_thresholds.length ? i.breached_thresholds.map((b) => <li key={b}>{b}</li>) : <li className="muted">no thresholds reported</li>}</ul>
                      <MiniLoop stages={stages} />
                      <p className="inc__foot muted small">
                        {det ? `${det.recovery_attempts.length} recovery attempt${det.recovery_attempts.length === 1 ? '' : 's'}` : 'detail not loaded yet'}
                        {recovered && <> · recovered in {dur(i.detected_at, recovered.at)}</>}
                        {i.evidence_sha256 && <> · evidence sealed</>}
                      </p>
                      <span className="inc__go" aria-hidden="true">→</span>
                    </Tilt>
                  </Link>
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </div>
  );
}
