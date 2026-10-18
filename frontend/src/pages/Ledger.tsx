import { useMemo, useState } from 'react';
import { useSentinel } from '../api/source';
import type { TimelineEvent } from '../api/types';
import { useMission } from '../state/mission';
import { EVENT_KIND, Empty, EventList, PageHead, dateTime, kindOf } from '../ui/kit';

const KINDS = [['all', 'All'], ['deploy', 'Deploy'], ['health', 'Health'], ['recovery', 'Recovery'], ['ai', 'AI · advisory'], ['gate', 'Gates']] as const;
type Kind = (typeof KINDS)[number][0];
const KCOL: Record<string, string> = { deploy: '#ffc23d', health: '#3cf0ff', recovery: '#ff8a3d', ai: '#a77bff', gate: '#2bff88' };

function Strip({ events, onPick }: { events: TimelineEvent[]; onPick: (e: TimelineEvent) => void }) {
  if (events.length < 2) return null;
  const ts = events.map((e) => Date.parse(e.at));
  const t0 = Math.min(...ts), t1 = Math.max(...ts), span = Math.max(1, t1 - t0);
  return (
    <div className="strip" data-reveal>
      <div className="strip__track">
        {events.map((e, i) => {
          const k = kindOf(e.type);
          const bad = e.data?.verdict === 'FAIL' || e.type === 'incident.detected';
          return (
            <button key={e.id} className={`strip__dot${bad ? ' is-bad' : ''}`} style={{ left: `${((ts[i] - t0) / span) * 100}%`, ['--c' as string]: bad ? '#ff2e63' : KCOL[k], ['--row' as string]: KINDS.findIndex(([x]) => x === k) - 1 }}
              onClick={() => onPick(e)} data-cursor={EVENT_KIND[e.type]?.label ?? e.type} aria-label={`${e.type} at ${dateTime(e.at)}`} />
          );
        })}
      </div>
      <div className="strip__axis"><span>{dateTime(new Date(t0).toISOString())}</span><span>{dateTime(new Date(t1).toISOString())}</span></div>
    </div>
  );
}

export default function Ledger() {
  const { snap, source } = useSentinel();
  const { now } = useMission();
  const [kind, setKind] = useState<Kind>('all');
  const [inc, setInc] = useState('all');
  const [q, setQ] = useState('');
  const [newest, setNewest] = useState(true);
  const all = snap.events;
  const incidents = useMemo(() => [...new Set(all.map((e) => e.incident_id).filter((x): x is string => !!x))], [all]);
  const list = useMemo(() => {
    const ql = q.trim().toLowerCase();
    const out = all.filter((e) => (kind === 'all' || kindOf(e.type) === kind) && (inc === 'all' || e.incident_id === inc)
      && (!ql || [e.type, e.summary, e.source, e.job, e.incident_id, e.commit_sha].some((x) => x?.toLowerCase().includes(ql))));
    return newest ? out.slice().reverse() : out;
  }, [all, kind, inc, q, newest]);
  const jump = (e: TimelineEvent) => {
    setKind('all'); setInc('all'); setQ('');
    setTimeout(() => document.getElementById(`ev-${e.id}`)?.scrollIntoView({ block: 'center' }), 50);
  };

  return (
    <div className="page">
      <PageHead num="04" kicker="Ledger · the record of record" title="Ledger">
        <p>Every event the CI jobs, scripts and the AI flow reported, with the job that reported it. If it is not in the ledger, Sentinel does not claim it happened.</p>
        {source === 'live' && <p className="muted small">The API has no global event feed yet, so this merges the timelines of the 12 most recent incidents.</p>}
      </PageHead>

      <section className="sec sec--tight">
        <Strip events={all} onPick={jump} />
        <div className="filters" data-reveal>
          <div className="seg" role="group" aria-label="Event kind">
            {KINDS.map(([k, l]) => (
              <button key={k} className={`seg__b${kind === k ? ' is-on' : ''}`} onClick={() => setKind(k)} aria-pressed={kind === k} style={{ ['--c' as string]: KCOL[k] ?? '#e9f1f4' }} data-cursor="Filter">
                {l}<small>{k === 'all' ? all.length : all.filter((e) => kindOf(e.type) === k).length}</small>
              </button>
            ))}
          </div>
          <div className="filters__row">
            <label className="field"><span>Incident</span>
              <select value={inc} onChange={(e) => setInc(e.target.value)}>
                <option value="all">All incidents</option>
                {incidents.map((i) => <option key={i} value={i}>{i}</option>)}
              </select>
            </label>
            <label className="field field--grow"><span>Search</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="type, job, commit, text…" /></label>
            <button className="seg__b" onClick={() => setNewest((x) => !x)} data-cursor="Order">{newest ? 'Newest first ↓' : 'Oldest first ↑'}</button>
          </div>
        </div>
        {list.length ? <div className="ledger-wrap"><EventList events={list} showIncident now={now} /></div>
          : <Empty title={all.length ? 'Nothing matches these filters.' : 'Nothing recorded yet.'} />}
      </section>
    </div>
  );
}
