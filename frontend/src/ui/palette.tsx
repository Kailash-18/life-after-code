/** ⌘K / Ctrl+K command palette: jump to any page or incident, or drive the demo. Doubles as the mobile menu. */
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSentinel } from '../api/source';
import { statusWord } from './kit';

export const PAGES = [
  { to: '/', label: 'Mission Control', hint: 'overview' },
  { to: '/rollout', label: 'Rollout', hint: 'releases · canary · evaluator' },
  { to: '/incidents', label: 'Incidents', hint: 'every regression caught' },
  { to: '/gates', label: 'Gates', hint: 'regression proof · Integrity Gate' },
  { to: '/ledger', label: 'Ledger', hint: 'every recorded event' },
  { to: '/system', label: 'System', hint: 'link · authority · wiring' },
];

interface Cmd { id: string; label: string; hint: string; group: string; run: () => void }

export function Palette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const { snap, source, startDemo, exitDemo } = useSentinel();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  const cmds = useMemo<Cmd[]>(() => [
    ...PAGES.map((p) => ({ id: p.to, label: p.label, hint: p.hint, group: 'Go to', run: () => nav(p.to) })),
    ...(snap.incidents ?? []).map((i) => ({ id: `inc-${i.id}`, label: i.id, hint: statusWord(i.status), group: 'Incident room', run: () => nav(`/incidents/${encodeURIComponent(i.id)}`) })),
    { id: 'demo-ok', label: 'Play the demo incident', hint: 'success path · scripted', group: 'Demo', run: () => startDemo(false) },
    { id: 'demo-fail', label: 'Play the failure path', hint: 'gates block the repair · scripted', group: 'Demo', run: () => startDemo(true) },
    ...(source === 'demo' ? [{ id: 'demo-exit', label: 'Exit demo, use the live API', hint: 'live', group: 'Demo', run: exitDemo }] : []),
  ], [snap.incidents, source, nav, startDemo, exitDemo]);

  const list = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return ql ? cmds.filter((c) => `${c.label} ${c.hint} ${c.group}`.toLowerCase().includes(ql)) : cmds;
  }, [cmds, q]);

  useEffect(() => { if (open) { setQ(''); setSel(0); setTimeout(() => input.current?.focus(), 30); } }, [open]);
  useEffect(() => setSel(0), [q]);

  if (!open) return null;
  const run = (c?: Cmd) => { if (!c) return; onClose(); c.run(); };
  const key = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(list.length - 1, s + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); run(list[sel]); }
    else if (e.key === 'Escape') onClose();
  };
  let lastGroup = '';
  return (
    <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette__box" onKeyDown={key}>
        <div className="palette__in">
          <span aria-hidden="true">⌘</span>
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Jump to a page, an incident, or an action…" aria-label="Search commands" />
          <kbd>esc</kbd>
        </div>
        <ul className="palette__list" role="listbox">
          {list.map((c, i) => {
            const head = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            return (
              <li key={c.id} role="option" aria-selected={i === sel}>
                {head && <span className="palette__group">{head}</span>}
                <button className={`palette__item${i === sel ? ' is-sel' : ''}`} onMouseEnter={() => setSel(i)} onClick={() => run(c)} data-cursor="Go">
                  <b>{c.label}</b><span>{c.hint}</span><i aria-hidden="true">↵</i>
                </button>
              </li>
            );
          })}
          {!list.length && <li className="palette__none">Nothing matches.</li>}
        </ul>
      </div>
    </div>
  );
}
