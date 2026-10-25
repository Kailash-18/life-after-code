/** Shared building blocks for every Mission Control page. */
import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { TimelineEvent } from '../api/types';
import { FAILURE_COPY, isFailure, type StageState, type StageView } from '../state/derive';
import { Scramble, Tilt } from './fx';

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

export function useNow(every = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), every); return () => clearInterval(t); }, [every]);
  return now;
}

/* ---------------- Tones ---------------- */
export type Tone = 'ok' | 'bad' | 'warn' | 'ai' | 'proof' | 'mute' | 'live';
export function statusTone(s: string): Tone {
  if (s === 'RECOVERED') return 'proof';
  if (isFailure(s)) return 'bad';
  if (s === 'DETECTED' || s === 'OPEN') return 'bad';
  if (s === 'INVESTIGATING' || s === 'REPAIR_PROPOSED') return 'ai';
  return 'warn';
}
export const statusWord = (s: string) => FAILURE_COPY[s] ?? s.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());

export function Chip({ tone = 'mute', children, pulse }: { tone?: Tone; children: ReactNode; pulse?: boolean }) {
  return <span className={`chip chip--${tone}${pulse ? ' chip--pulse' : ''}`}><i aria-hidden="true" />{children}</span>;
}

/* ---------------- Page header ---------------- */
export function PageHead({ num: n, kicker, title, children, aside }: { num: string; kicker: string; title: string; children?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="phead">
      <div className="phead__k" data-reveal><span className="phead__num">{n}</span><span>{kicker}</span></div>
      <Scramble as="h1" className="phead__title" text={title} />
      {children && <div className="phead__sub" data-reveal>{children}</div>}
      {aside && <div className="phead__aside" data-reveal>{aside}</div>}
    </header>
  );
}

export function SecHead({ num: n, title, children }: { num?: string; title: string; children?: ReactNode }) {
  return (
    <header className="sec__head sec__head--sm" data-reveal>
      {n && <span className="sec__num">{n}</span>}
      <Scramble as="h2" text={title} />
      {children && <p>{children}</p>}
    </header>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty" data-reveal><p className="empty__big">{title}</p>{children && <p className="muted">{children}</p>}</div>;
}

/* ---------------- Hash with copy ---------------- */
export function Sha({ value, label }: { value?: string; label?: string }) {
  const [done, setDone] = useState(false);
  if (!value) return <span className="sha sha--none">{label ? `${label}: ` : ''}not recorded</span>;
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setDone(true); setTimeout(() => setDone(false), 1400); } catch { /* clipboard blocked */ }
  };
  return (
    <button className={`sha${done ? ' is-done' : ''}`} onClick={copy} data-cursor={done ? 'Copied' : 'Copy'} title="Copy">
      {label && <span className="sha__l">{label}</span>}
      <code>{value}</code>
      <span className="sha__c" aria-live="polite">{done ? 'copied' : 'copy'}</span>
    </button>
  );
}

/* ---------------- Stage visuals ---------------- */
export const STATE_WORD: Record<StageState, string> = {
  waiting: 'Not reached', active: 'Underway', sourced: 'Sourced', unsourced: 'Recorded · no source',
  advisory: 'AI · advisory', failed: 'Failed', blocked: 'Blocked', confirmed: 'Confirmed',
};

/** Nine segments, one per recovery stage. */
export function MiniLoop({ stages }: { stages: StageView[] }) {
  return (
    <ol className="miniloop" aria-label="Recovery stages">
      {stages.map((s) => <li key={s.stage} className={`ml ml--${s.state}`} title={`${s.label}: ${STATE_WORD[s.state]}`}><span className="sr-only">{s.label}: {STATE_WORD[s.state]}</span></li>)}
    </ol>
  );
}

export function StageCard({ s }: { s: StageView }) {
  return (
    <Tilt className={`stage stage--${s.state}`} max={14}>
      <span className="stage__n">{String(s.n).padStart(2, '0')}</span>
      <span className="stage__chip">{STATE_WORD[s.state]}</span>
      <h3 className="stage__label">{s.label}</h3>
      <p className="stage__auth">Decided by {s.authority}.</p>
      {s.event ? (
        <div className="stage__ev">
          <p>{s.event.summary ?? s.event.type}</p>
          <p className="stage__src"><code>{s.event.source}</code>{s.event.job && <code>job {s.event.job}</code>}<time>{time(s.event.at)}</time>
            {s.event.evidence_url && <a href={s.event.evidence_url} target="_blank" rel="noreferrer" data-cursor="Open">evidence ↗</a>}</p>
        </div>
      ) : <p className="stage__none">{s.state === 'blocked' ? 'Not reached: an earlier stage failed (derived).' : 'No source event recorded.'}</p>}
    </Tilt>
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
  if (e.rejected) return 'is-refused';
  const v = e.data?.verdict;
  if (kindOf(e.type) === 'ai') return 'is-ai';
  if (e.type === 'recovery.verified') return 'is-proof';
  if (v === 'FAIL' || e.type === 'incident.detected' || e.type === 'rollback.started' || e.data?.outcome === 'no_fix_found') return 'is-bad';
  if (v === 'PASS') return 'is-ok';
  return '';
}

/** The measured values an event carries, as small labelled readouts. */
export function EventData({ e }: { e: TimelineEvent }) {
  const d = e.data ?? {};
  const items: [string, string][] = [];
  if (typeof d.verdict === 'string') items.push(['verdict', d.verdict]);
  if (typeof d.target === 'string') items.push(['target', d.target]);
  const tp = num(d.traffic_percent); if (tp !== undefined) items.push(['traffic', `${tp}%`]);
  const er = num(d.error_rate); if (er !== undefined) items.push(['errors', pct(er)]);
  const p = num(d.p95_ms); if (p !== undefined) items.push(['p95', ms(p)]);
  const n = num(d.sample_size); if (n !== undefined) items.push(['samples', String(n)]);
  if (typeof d.outcome === 'string') items.push(['outcome', d.outcome]);
  const mr = num(d.mr_iid); if (mr !== undefined) items.push(['MR', `!${mr}`]);
  if (Array.isArray(d.findings) && d.findings.length) items.push(['findings', String(d.findings.length)]);
  if (!items.length) return null;
  return <dl className="evdata">{items.map(([k, v]) => <div key={k} className={k === 'verdict' ? `v-${v.toLowerCase()}` : ''}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>;
}

export function EventList({ events, showIncident, now }: { events: TimelineEvent[]; showIncident?: boolean; now?: number }) {
  return (
    <ol className="ledger">
      {events.map((e) => {
        const ai = kindOf(e.type) === 'ai';
        return (
          <li key={e.id} id={`ev-${e.id}`} className={eventTone(e)} data-reveal>
            <time title={e.at}>{time(e.at)}<small>{now ? ago(e.at, now) : ''}</small></time>
            <div>
              <p className="ledger__type">{EVENT_KIND[e.type]?.label ?? e.type}<code>{e.type}</code>{ai && <span className="tag-ai">AI · advisory</span>}{e.rejected && <span className="tag-refused">refused · {e.rejected.code}</span>}</p>
              {e.rejected ? <p className="ledger__refused">{e.rejected.message} This event did not change the incident.</p> : e.summary && <p>{e.summary}</p>}
              <EventData e={e} />
              <p className="ledger__src">
                <code>{e.source}</code>{e.job && <code>job {e.job}</code>}
                {showIncident && e.incident_id && <Link to={`/incidents/${encodeURIComponent(e.incident_id)}`} data-cursor="Room">{e.incident_id} →</Link>}
                {e.evidence_url && <a href={e.evidence_url} target="_blank" rel="noreferrer" data-cursor="Open">evidence ↗</a>}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------- Ring gauge ---------------- */
export function Ring({ value, max = 100, label, sub, color }: { value: number | null; max?: number; label: string; sub?: string; color: string }) {
  const r = 52, c = 2 * Math.PI * r;
  const f = value === null ? 0 : Math.max(0, Math.min(1, value / max));
  return (
    <div className="ring" style={{ ['--c' as string]: color }}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r={r} className="ring__bg" />
        <circle cx="60" cy="60" r={r} className="ring__fg" strokeDasharray={c} strokeDashoffset={c * (1 - f)} />
        {Array.from({ length: 24 }, (_, i) => <line key={i} x1="60" y1="2" x2="60" y2={i % 6 ? 6 : 10} transform={`rotate(${i * 15} 60 60)`} className="ring__tick" />)}
      </svg>
      <div className="ring__v"><b>{value === null ? '—' : label}</b>{sub && <span>{sub}</span>}</div>
    </div>
  );
}
