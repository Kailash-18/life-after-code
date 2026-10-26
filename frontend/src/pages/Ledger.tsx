import { useMemo, useState } from 'react';
import { useSentinel } from '../api/source';
import { useMission } from '../state/mission';
import { Empty, EventList, PageHead, kindOf } from '../ui/kit';

const KINDS = [['all', 'All'], ['deploy', 'Deploy'], ['health', 'Health'], ['recovery', 'Recovery'], ['ai', 'AI'], ['gate', 'Gates']] as const;
type Kind = (typeof KINDS)[number][0];

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
  const refused = all.filter((e) => e.rejected).length;

  return (
    <>
      <PageHead eyebrow="Ledger" title="Every recorded event">
        What the CI jobs, scripts and the AI flow reported, and which job reported it. If it is not in the ledger, Sentinel does not claim it happened.
        {refused > 0 && <> {refused} event{refused === 1 ? ' was' : 's were'} refused by the backend and changed nothing.</>}
        {source === 'live' && <span className="muted"> Read from <code>/api/v1/events</code>.</span>}
      </PageHead>

      <div className="filters">
        <div className="seg" role="group" aria-label="Event kind">
          {KINDS.map(([k, l]) => (
            <button key={k} className={kind === k ? 'is-on' : ''} onClick={() => setKind(k)} aria-pressed={kind === k}>
              {l}<small>{k === 'all' ? all.length : all.filter((e) => kindOf(e.type) === k).length}</small>
            </button>
          ))}
        </div>
        <select value={inc} onChange={(e) => setInc(e.target.value)} aria-label="Incident">
          <option value="all">All incidents</option>
          {incidents.map((i) => <option key={i} value={i}>{i}</option>)}
        </select>
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search type, job, commit, text" aria-label="Search events" />
        <button className="btn btn--sm" onClick={() => setNewest((x) => !x)}>{newest ? 'Newest first' : 'Oldest first'}</button>
      </div>

      {list.length ? <EventList events={list} showIncident now={now} /> : <Empty title={all.length ? 'Nothing matches these filters.' : 'Nothing recorded yet.'} />}
    </>
  );
}
