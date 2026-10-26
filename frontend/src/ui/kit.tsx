/** Shared building blocks for every Mission Control page. */
import { memo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { TimelineEvent } from '../api/types';
import { FAILURE_COPY, isFailure, type StageState, type StageView } from '../state/derive';
import { CountUp, Scramble } from './fx';
import { Icon } from './icons';

/* ---------------- Formatting ---------------- */
export const pct = (v: number) => `${(v * 100).toFixed(v < 0.01 ? 2 : 1)}%`;
export const ms = (v: number) => `${Math.round(v)} ms`;
export const time = (iso?: string) => {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};
export const dateTime = (iso?: string) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};
export function ago(iso: string | number | undefined, now = Date.now()) {
  if (iso === undefined) return '—';
  const t = typeof iso === 'number' ? iso : Date.parse(iso);
  if (!Number.isFinite(t)) return '—';
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
export const spanMs = (v: number) => {
  const s = Math.round(Math.abs(v) / 1000);
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
};
export const dur = (a?: string, b?: string) => {
  const x = Date.parse(a ?? ''), y = Date.parse(b ?? '');
  return !Number.isFinite(x) || !Number.isFinite(y) ? '—' : spanMs(y - x);
};
export const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);

/* ---------------- Tones ---------------- */
export type Tone = 'ok' | 'bad' | 'warn' | 'ai' | 'info' | 'mute';
export function statusTone(s: string): Tone {
  if (s === 'RECOVERED') return 'ok';
  if (isFailure(s) || s === 'DETECTED' || s === 'OPEN') return 'bad';
  if (s === 'INVESTIGATING' || s === 'REPAIR_PROPOSED') return 'ai';
  return 'warn';
}
export const statusWord = (s: string) => FAILURE_COPY[s] ?? s.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());

export function Badge({ tone = 'mute', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

/* ---------------- Page structure ---------------- */
export function PageHead({ eyebrow, title, children, aside }: { eyebrow: string; title: ReactNode; children?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="phead">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        {typeof title === 'string' ? <Scramble as="h1" text={title} duration={650} /> : <h1>{title}</h1>}
      </div>
      {children && <div className="lede">{children}</div>}
      {aside && <div className="phead__aside">{aside}</div>}
    </header>
  );
}

export function Section({ title, note, children, id }: { title: string; note?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="sec" id={id}>
      <header className="sec__head"><h2>{title}</h2>{note && <p>{note}</p>}</header>
      {children}
    </section>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><b>{title}</b>{children}</div>;
}

export function Metric({ value, label, tone }: { value: ReactNode; label: string; tone?: 'ok' | 'bad' }) {
  return <div className={`metric${tone ? ` metric--${tone}` : ''}`}><b><CountUp value={value} /></b><span>{label}</span></div>;
}

/* ---------------- Hash with copy ---------------- */
export function Sha({ value, label }: { value?: string; label?: string }) {
  const [done, setDone] = useState(false);
  if (!value) return <span className="sha sha--none">{label ? `${label} ` : ''}not recorded</span>;
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setDone(true); setTimeout(() => setDone(false), 1200); } catch { /* clipboard blocked */ }
  };
  return (
    <button className="sha" onClick={copy} title={done ? 'Copied' : 'Copy'}>
      {label && <em>{label}</em>}<code>{value}</code>{done && <em>copied</em>}
    </button>
  );
}

/* ---------------- Recovery stages ---------------- */
export const STATE_WORD: Record<StageState, string> = {
  waiting: 'Not reached', active: 'In progress', sourced: 'Done', unsourced: 'Done · no source event',
  advisory: 'AI · advisory', failed: 'Failed', blocked: 'Not reached', confirmed: 'Confirmed',
};

/** The nine stages as a horizontal track (vertical on narrow screens). */
export const Track = memo(function Track({ stages }: { stages: StageView[] }) {
  return (
    <ol className="track" aria-label="Recovery stages">
      {stages.map((s) => (
        <li key={s.stage} className={`step step--${s.state}`} style={{ ['--i' as string]: s.n - 1 }}>
          <span className="step__node">
            {s.state === 'failed' ? <Icon name="x" /> : ['sourced', 'unsourced', 'confirmed'].includes(s.state) ? <Icon name="check" /> : s.state === 'advisory' ? <Icon name="ai" /> : s.n}
          </span>
          {s.n > 1 && ['sourced', 'unsourced', 'confirmed', 'advisory', 'active'].includes(s.state) && <span className="step__flow" aria-hidden="true" />}
          <span className="step__label">{s.label}</span>
          <span className="step__state">{STATE_WORD[s.state]}</span>
        </li>
      ))}
    </ol>
  );
}, (a, b) => a.stages.map((x) => x.state).join() === b.stages.map((x) => x.state).join());

export function Mini({ stages }: { stages: StageView[] }) {
  return (
    <span className="mini" aria-label={stages.map((s) => `${s.label}: ${STATE_WORD[s.state]}`).join(', ')}>
      {stages.map((s) => <i key={s.stage} className={`m-${s.state}`} />)}
    </span>
  );
}

/* ---------------- Events ---------------- */
export const EVENT_KIND: Record<string, { kind: 'deploy' | 'health' | 'recovery' | 'ai' | 'gate'; label: string }> = {
  'pipeline.started': { kind: 'deploy', label: 'Pipeline started' },
  'deploy.canary_started': { kind: 'deploy', label: 'Canary step' },
  'evaluator.verdict': { kind: 'health', label: 'Evaluator verdict' },
  'incident.detected': { kind: 'health', label: 'Incident opened' },
  'rollback.started': { kind: 'recovery', label: 'Rollback started' },
  'rollback.completed': { kind: 'recovery', label: 'Rollback completed' },
  'evidence.collected': { kind: 'recovery', label: 'Evidence sealed' },
  'flow.started': { kind: 'ai', label: 'AI flow started' },
  'flow.completed': { kind: 'ai', label: 'AI flow finished' },
  'repair.proposed': { kind: 'ai', label: 'Repair proposed' },
  'regression_proof.verdict': { kind: 'gate', label: 'Regression proof' },
  'integrity_gate.verdict': { kind: 'gate', label: 'Integrity Gate' },
  'merge.completed': { kind: 'gate', label: 'Merged' },
  'redeploy.completed': { kind: 'deploy', label: 'Redeploy completed' },
  'recovery.verified': { kind: 'health', label: 'Recovery verified' },
};
export const kindOf = (t: string) => EVENT_KIND[t]?.kind ?? 'deploy';

function eventTone(e: TimelineEvent): string {
  if (e.rejected) return 'refused';
  if (kindOf(e.type) === 'ai') return 'ai';
  if (e.type === 'recovery.verified') return 'proof';
  const v = e.data?.verdict;
  if (v === 'FAIL' || e.type === 'incident.detected' || e.type === 'rollback.started' || e.data?.outcome === 'no_fix_found') return 'bad';
  if (v === 'PASS') return 'ok';
  return '';
}

/** The measured values an event carries. Only fields the event actually has are shown. */
export function Readouts({ e }: { e: TimelineEvent }) {
  const d = e.data ?? {};
  const items: [string, string][] = [];
  if (typeof d.verdict === 'string') items.push(['verdict', d.verdict]);
  const tp = num(d.traffic_percent); if (tp !== undefined) items.push(['traffic', `${tp}%`]);
  const er = num(d.error_rate); if (er !== undefined) items.push(['errors', pct(er)]);
  const p = num(d.p95_ms); if (p !== undefined) items.push(['p95', ms(p)]);
  const n = num(d.sample_size); if (n !== undefined) items.push(['samples', String(n)]);
  const pv = num(d.p_value); if (pv !== undefined) items.push(['p-value', pv < 0.001 ? '< 0.001' : pv.toFixed(3)]);
  if (typeof d.outcome === 'string') items.push(['outcome', d.outcome]);
  const mr = num(d.mr_iid); if (mr !== undefined) items.push(['MR', `!${mr}`]);
  if (Array.isArray(d.findings) && d.findings.length) items.push(['findings', String(d.findings.length)]);
  if (!items.length) return null;
  return <dl className="readouts">{items.map(([k, v]) => <div key={k} className={k === 'verdict' ? `v-${v.toLowerCase()}` : ''}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>;
}

export const EventList = memo(function EventList({ events, showIncident, now }: { events: TimelineEvent[]; showIncident?: boolean; now?: number }) {
  return (
    <ol className="events">
      {events.map((e) => (
        <li key={e.id} id={`ev-${e.id}`} className={`ev ev--${eventTone(e)}`}>
          <time dateTime={e.at} title={e.at}>{time(e.at)}<small>{now ? ago(e.at, now) : dateTime(e.at)}</small></time>
          <span className="ev__mark" aria-hidden="true" />
          <div>
            <p className="ev__head">
              {EVENT_KIND[e.type]?.label ?? e.type}<code>{e.type}</code>
              {kindOf(e.type) === 'ai' && <Badge tone="ai">advisory</Badge>}
              {e.rejected && <Badge tone="bad">refused · {e.rejected.code}</Badge>}
            </p>
            {e.rejected ? <p className="ev__refused">{e.rejected.message} This event did not change the incident.</p> : e.summary && <p className="ev__body">{e.summary}</p>}
            <Readouts e={e} />
            <p className="ev__src">
              <code>{e.source}</code>{e.job && <span>job {e.job}</span>}
              {showIncident && e.incident_id && <Link to={`/incidents/${encodeURIComponent(e.incident_id)}`}>{e.incident_id}</Link>}
              {e.evidence_url && <a href={e.evidence_url} target="_blank" rel="noreferrer">evidence ↗</a>}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}, (a, b) => a.showIncident === b.showIncident && a.events.length === b.events.length && a.events.every((e, k) => e.id === b.events[k].id && e.rejected === b.events[k].rejected) && Math.floor((a.now ?? 0) / 15000) === Math.floor((b.now ?? 0) / 15000));
