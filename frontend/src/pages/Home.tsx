import { Link } from 'react-router-dom';
import { useSentinel } from '../api/source';
import { End, Hero, Loop, Outcome, Pulse } from '../sections/Sections';
import { isFailure } from '../state/derive';
import { useMission } from '../state/mission';
import { Scramble, Tilt } from '../ui/fx';
import { ago } from '../ui/kit';

function Modules() {
  const { snap, endpoints, source } = useSentinel();
  const { d, now } = useMission();
  const inc = snap.incidents ?? [];
  const open = inc.filter((i) => i.status !== 'RECOVERED' && !isFailure(i.status)).length;
  const gates = Object.values(snap.details).flatMap((x) => x.recovery_attempts.flatMap((a) => a.gate_results)).filter((g) => g.gate === 'integrity');
  const blocks = gates.filter((g) => g.verdict === 'fail').length;
  const rel = snap.releases ?? [];
  const rollbacks = rel.filter((r) => r.status === 'ROLLED_BACK').length;
  const split = snap.status?.traffic_split;
  const eps = Object.values(endpoints);
  const last = snap.events[snap.events.length - 1];
  const tiles = [
    { to: '/rollout', n: '01', name: 'Rollout', big: snap.status?.current_release?.version ?? '—', unit: 'serving',
      line: split && split.candidate_percent > 0 ? `${split.candidate_percent}% on candidate ${snap.status?.candidate_release?.version ?? ''}` : `${rel.length} releases · ${rollbacks} rolled back`, tone: split && split.candidate_percent > 0 ? 'warn' : 'ok' },
    { to: '/incidents', n: '02', name: 'Incidents', big: String(open), unit: open === 1 ? 'open' : 'open',
      line: `${inc.length} recorded · ${inc.filter((i) => i.status === 'RECOVERED').length} recovered · ${inc.filter((i) => isFailure(i.status)).length} stopped`, tone: open ? 'bad' : 'ok' },
    { to: '/gates', n: '03', name: 'Gates', big: String(blocks), unit: blocks === 1 ? 'repair blocked' : 'repairs blocked',
      line: `${gates.length} Integrity Gate verdicts recorded · 9 rules armed`, tone: blocks ? 'warn' : 'ok' },
    { to: '/ledger', n: '04', name: 'Ledger', big: String(snap.events.length), unit: 'events',
      line: last ? `last: ${last.type} · ${ago(last.at, now)}` : 'nothing recorded yet', tone: 'ok' },
    { to: '/system', n: '05', name: 'System', big: source === 'demo' ? 'DEMO' : `${eps.filter((e) => e.ok).length}/${eps.length || 7}`, unit: source === 'demo' ? 'scripted' : 'endpoints answering',
      line: snap.healthz ? `healthz: ${snap.healthz.status}${snap.healthz.version ? ` · v${snap.healthz.version}` : ''}` : 'healthz not read yet', tone: source === 'demo' ? 'ai' : eps.some((e) => e.ok === false) ? 'bad' : 'ok' },
  ];
  return (
    <section id="modules" className="sec sec--modules">
      <header className="sec__head" data-reveal>
        <span className="sec__num">03</span>
        <Scramble as="h2" text="Mission modules" />
        <p>Every part of the loop has its own console. Numbers here are counted from what the API returned, nothing more.</p>
      </header>
      <div className="modules">
        {tiles.map((t) => (
          <Link key={t.to} to={t.to} className="module-link" data-cursor="Open" data-reveal>
            <Tilt className={`card module module--${t.tone}`} max={16}>
              <span className="module__n">{t.n}</span>
              <span className="module__name">{t.name}</span>
              <span className="module__big">{t.big}</span>
              <span className="module__unit">{t.unit}</span>
              <span className="module__line">{t.line}</span>
              <span className="module__go" aria-hidden="true">↗</span>
            </Tilt>
          </Link>
        ))}
      </div>
      {d.incident && (
        <p className="modules__room" data-reveal>
          {d.incidentActive ? 'Live incident' : 'Last incident'}: <Link to={`/incidents/${encodeURIComponent(d.incident.id)}`} data-cursor="Room">{d.incident.id} — open the incident room →</Link>
        </p>
      )}
    </section>
  );
}

export default function Home() {
  const { snap } = useSentinel();
  const { d } = useMission();
  const verified = d.stages.find((s) => s.stage === 'RECOVERED')?.event;
  return (
    <>
      <Hero d={d} />
      <Pulse d={d} />
      <Loop stages={d.stages} progress={d.progress}
        caption={d.incident
          ? <>Incident <code>{d.incident.id}</code> on release {d.version(d.incident.release_id)} · {d.incidentActive ? 'in progress' : 'last recorded incident'}. A stage lights only when the backend records it.</>
          : 'No incident yet. Every stage stays dark until the backend records one.'} />
      <Modules />
      <Outcome status={d.incident?.status ?? null} attempt={d.attempt} verified={verified} releases={snap.releases} num="04" />
      <section className="sec sec--endonly"><End /></section>
    </>
  );
}
