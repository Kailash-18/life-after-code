import { Link } from 'react-router-dom';
import { useSentinel } from '../api/source';
import { accepted, isFailure } from '../state/derive';
import { useMission } from '../state/mission';
import { HealthChart } from '../ui/chart';
import { RiseWords, Scramble } from '../ui/fx';
import { Icon } from '../ui/icons';
import { Badge, EventList, Metric, Section, Track, ago, ms, pct, spanMs, statusTone, statusWord } from '../ui/kit';

function Offline() {
  const { startDemo } = useSentinel();
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h3>Start the backend to see live data</h3>
      <p className="small muted" style={{ marginTop: 4 }}>Mission Control only reads. Every number comes from the Sentinel API, which records signed events from CI.</p>
      <pre className="cmd">{'cd backend\npip install -r requirements.txt\n$env:SENTINEL_HMAC_SECRET="local-secret"\nuvicorn app.main:app --port 8000\n\n'}<span className="c"># then, from the repo root, drive one incident through the loop:</span>{'\npython backend/scripts/smoke_e2e.py'}</pre>
      <div className="row" style={{ marginTop: 16 }}>
        <button className="btn btn--primary" onClick={() => startDemo(false)}><Icon name="play" />Demo: full recovery</button>
        <button className="btn" onClick={() => startDemo(true)}>Demo: gates block the fix</button>
      </div>
    </div>
  );
}

const PRINCIPLES = [
  { k: 'AI proposes', tone: 'ai', icon: 'ai', title: 'Duo investigates and writes a fix', body: 'It reads the sealed evidence and opens a merge request with a fix and a new regression test. Nothing it writes counts as proof.' },
  { k: 'Gates decide', tone: 'info', icon: 'gates', title: 'Deterministic jobs judge the fix', body: 'The test must fail on the broken release and pass on the fix. The Integrity Gate blocks any attempt to weaken or skip tests.' },
  { k: 'Evidence proves', tone: 'ok', icon: 'seal', title: 'Production has the last word', body: 'The fix ships through a canary. The incident is marked recovered only when the evaluator measures it healthy.' },
];

export default function Home() {
  const { snap, connected, source, readings, startDemo } = useSentinel();
  const { d, now } = useMission();
  const st = snap.status;
  const h = st?.system_health;
  const split = st?.traffic_split;
  const incidents = snap.incidents ?? [];
  const recovered = incidents.filter((i) => i.status === 'RECOVERED');
  const stopped = incidents.filter((i) => isFailure(i.status));
  const ttr = recovered.map((i) => {
    const v = snap.timelines[i.id]?.find((e) => !e.rejected && e.type === 'recovery.verified');
    const det = i.detected_at || snap.timelines[i.id]?.find((e) => e.type === 'incident.detected')?.at;
    return v && det ? Date.parse(v.at) - Date.parse(det) : NaN;
  }).filter(Number.isFinite).sort((a, b) => a - b);
  const median = ttr.length ? ttr[Math.floor(ttr.length / 2)] : null;
  const inc = d.incident;
  const recent = accepted(snap.events).slice(-5).reverse();
  const offline = source === 'live' && connected === false && !st;
  const tone = d.mode === 'healthy' || d.mode === 'recovered' ? 'ok' : d.mode === 'offline' || d.mode === 'connecting' ? '' : d.mode === 'canary' || d.mode === 'contained' || d.mode === 'investigating' || d.mode === 'verifying' || d.mode === 'redeploying' ? 'warn' : 'bad';
  const word = offline ? 'API offline' : connected === null ? 'Connecting' : { healthy: 'All systems nominal', recovered: 'Recovered', canary: 'Canary in progress', degraded: 'Degraded', breach: 'Incident open', contained: 'Contained', investigating: 'Investigating', verifying: 'Verifying fix', redeploying: 'Redeploying', failed: 'Recovery stopped', offline: 'Offline', connecting: 'Connecting' }[d.mode];

  return (
    <>
      <div className="card hero hero--fx">
        <span className="orbit" aria-hidden="true" />
        <div className="hero__main">
          <span className="status-pill"><span className={`dot dot--${tone}${tone ? ' dot--live' : ''}`} /><Scramble text={word ?? ''} duration={500} /></span>
          <RiseWords className="headline" text={d.headline} />
          <p className="headline-sub">{d.sub}</p>
          <div className="hero__foot">
            {inc && <Link className="btn btn--primary shine" to={`/incidents/${encodeURIComponent(inc.id)}`}>Open {inc.id}<Icon name="arrow" /></Link>}
            {offline ? <button className="btn btn--primary" onClick={() => startDemo(false)}><Icon name="play" />Play the demo</button> : <Link className="btn" to="/ledger">View ledger</Link>}
          </div>
        </div>
        <div className="hero__chart"><HealthChart readings={readings} offline={offline} /></div>
        <div className="hero__kpis hero-wrap">
          <Metric value={st?.current_release?.version ?? '—'} label="Serving release" />
          <Metric value={split ? `${split.candidate_percent}%` : '—'} label={st?.candidate_release ? `Traffic on ${st.candidate_release.version}` : 'No candidate on trial'} />
          <Metric value={h ? pct(h.error_rate) : '—'} label="Error rate" tone={h && !h.healthy ? 'bad' : undefined} />
          <Metric value={h ? ms(h.p95_ms) : '—'} label="p95 latency" tone={h && !h.healthy ? 'bad' : undefined} />
        </div>
      </div>

      {offline && <Offline />}

      {!offline && (
        <Section title={d.incidentActive ? 'Active incident' : 'Latest incident'} note="A stage lights only when the incident record says the loop passed it.">
          {inc ? (
            <div className="card" style={{ padding: '20px 22px 24px' }}>
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: 26 }}>
                <div className="row">
                  <Link to={`/incidents/${encodeURIComponent(inc.id)}`} style={{ fontWeight: 600, textDecoration: 'none' }}>{inc.id}</Link>
                  <Badge tone={statusTone(inc.status)}>{statusWord(inc.status)}</Badge>
                </div>
                <span className="muted small">release {d.version(inc.release_id)} · detected {ago(inc.detected_at, now)}</span>
              </div>
              <Track stages={d.stages} />
            </div>
          ) : <div className="empty"><b>No incident recorded.</b><span className="muted small">The loop is armed. The first regression the evaluator catches appears here.</span></div>}
        </Section>
      )}

      {!offline && (
        <Section title="Track record">
          <div className="grid g4">
            <div className="card tilt"><Metric value={incidents.length} label="Regressions caught" /></div>
            <div className="card tilt"><Metric value={recovered.length} label="Recovered, proven in production" tone={recovered.length ? 'ok' : undefined} /></div>
            <div className="card tilt"><Metric value={stopped.length} label="Stopped instead of shipping an unproven fix" /></div>
            <div className="card tilt"><Metric value={median === null ? '—' : spanMs(median)} label="Median time to verified recovery" /></div>
          </div>
        </Section>
      )}

      <Section title="How Sentinel decides">
        <div className="principles">
          {PRINCIPLES.map((p, i) => (
            <div key={p.k} className="card tilt principle">
              <span className="glyph" style={{ background: `var(--${p.tone}-bg)`, color: `var(--${p.tone})` }}><Icon name={p.icon} /></span>
              <span className="step-k" style={{ color: `var(--${p.tone})` }}>0{i + 1} · {p.k}</span>
              <h3>{p.title}</h3>
              <p>{p.body}</p>
            </div>
          ))}
        </div>
      </Section>

      {recent.length > 0 && (
        <Section title="Latest events" note={<Link to="/ledger">Full ledger →</Link>}>
          <EventList events={recent} showIncident now={now} />
        </Section>
      )}
    </>
  );
}
