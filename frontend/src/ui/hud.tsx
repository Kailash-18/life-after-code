import { useEffect, useRef, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { API_BASE, getApiKey } from '../api/client';
import { useSentinel, type Reading } from '../api/source';
import { bus } from '../state/bus';
import { MODE_COLOR, isFailure, type SceneMode } from '../state/derive';
import { ApiKeyModal } from './ApiKeyModal';
import { PAGES } from './palette';
import { MagButton } from './fx';

/* ---------------- Boot sequence ---------------- */
export function Boot({ onDone }: { onDone: () => void }) {
  const [n, setN] = useState(0);
  const [lines, setLines] = useState<string[]>([]);
  const [out, setOut] = useState(false);
  useEffect(() => {
    if (bus.reducedMotion) { onDone(); return; }
    const script = ['SENTINEL // DEPLOYMENT SAFETY CORE', 'linking read API ............ ok', 'loading recovery loop (9 stages) ok', 'arming deterministic gates ... ok', 'AI channel: ADVISORY ONLY'];
    const t0 = performance.now(); let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / 1900);
      setN(Math.round(p * 100));
      setLines(script.slice(0, Math.ceil(p * script.length)));
      if (p < 1) raf = requestAnimationFrame(tick);
      else { setOut(true); bus.pulse(2); setTimeout(onDone, 750); }
    };
    raf = requestAnimationFrame(tick);
    const skip = () => { cancelAnimationFrame(raf); setOut(true); setTimeout(onDone, 500); };
    addEventListener('keydown', skip, { once: true });
    return () => { cancelAnimationFrame(raf); removeEventListener('keydown', skip); };
  }, [onDone]);
  return (
    <div className={`boot${out ? ' is-out' : ''}`} aria-hidden="true">
      <div className="boot__num">{String(n).padStart(3, '0')}</div>
      <pre className="boot__log">{lines.map((l) => `> ${l}`).join('\n')}<span className="boot__caret">_</span></pre>
      <div className="boot__bar"><span style={{ width: `${n}%` }} /></div>
    </div>
  );
}

/* ---------------- Top HUD ---------------- */
function ago(ms: number) {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.round(s / 60)}m`;
}

export function TopBar({ mode, onMenu }: { mode: SceneMode; onMenu: () => void }) {
  const { source, connected, lastOkAt, stale, snap } = useSentinel();
  const [now, setNow] = useState(Date.now());
  const [apiKey, setLocalApiKey] = useState(getApiKey());
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false);

  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);

  useEffect(() => {
    const handleKeyChange = (e: Event) => {
      const customEvent = e as CustomEvent<{ apiKey: string }>;
      if (customEvent.detail?.apiKey) setLocalApiKey(customEvent.detail.apiKey);
    };
    const handleOpenModal = () => setApiKeyModalOpen(true);

    window.addEventListener('sentinel:apikey:changed', handleKeyChange);
    window.addEventListener('sentinel:open:apikey:modal', handleOpenModal);
    return () => {
      window.removeEventListener('sentinel:apikey:changed', handleKeyChange);
      window.removeEventListener('sentinel:open:apikey:modal', handleOpenModal);
    };
  }, []);

  const linkState = source === 'demo' ? 'demo' : connected === null ? 'linking' : !connected ? 'offline' : stale ? 'stale' : 'live';
  const linkText = {
    demo: 'Demo scenario', linking: 'Linking…', offline: 'API offline',
    stale: `Stale · ${lastOkAt ? ago(now - lastOkAt) : '?'} ago`, live: `Live · ${lastOkAt ? ago(now - lastOkAt) : '0s'} ago`,
  }[linkState];
  const open = (snap.incidents ?? []).filter((i) => i.status !== 'RECOVERED' && !isFailure(i.status)).length;
  return (
    <>
      <header className="top" style={{ ['--mode' as string]: MODE_COLOR[mode] }}>
        <NavLink to="/" className="brand" data-cursor="Home" end>
          <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3 28 10v12L16 29 4 22V10z" /><circle cx="16" cy="16" r="4.5" /></svg>
          <span>SENTINEL</span>
        </NavLink>
        <nav className="top__nav" aria-label="Pages">
          {PAGES.map((p) => (
            <NavLink key={p.to} to={p.to} end={p.to === '/'} className={({ isActive }) => `navl${isActive ? ' is-on' : ''}`} data-cursor={p.label}>
              {p.to === '/' ? 'Mission' : p.label}
              {p.to === '/incidents' && open > 0 && <span className="navl__badge">{open}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="top__right">
          <button
            className="link link--key"
            onClick={() => setApiKeyModalOpen(true)}
            data-cursor="Key"
            title="Sentinel API Key Credentials (Click to view or rotate)"
            style={{
              background: 'rgba(60, 240, 255, 0.08)',
              border: '1px solid rgba(60, 240, 255, 0.28)',
              padding: '6px 14px',
              borderRadius: '999px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              font: '600 11px/1 var(--mono)',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--cyan)',
              boxShadow: '0 0 14px -6px var(--cyan)',
            }}
          >
            <span aria-hidden="true" style={{ fontSize: '12px' }}>🔑</span>
            <span>API KEY: {apiKey.length > 14 ? `${apiKey.slice(0, 10)}…${apiKey.slice(-4)}` : apiKey}</span>
          </button>
          <div className={`link link--${linkState}`} role="status" title={source === 'live' ? `API: ${API_BASE || location.origin}` : 'Scripted demo data'}>
            <i aria-hidden="true" /> <span className="link__t">{linkText}</span>
          </div>
          <button className="kbtn" onClick={onMenu} data-cursor="Menu" aria-label="Open the command palette">
            <span className="kbtn__k">⌘K</span><span className="kbtn__m" aria-hidden="true"><i /><i /><i /></span>
          </button>
        </div>
      </header>
      <ApiKeyModal open={apiKeyModalOpen} onClose={() => setApiKeyModalOpen(false)} />
    </>
  );
}

export function DemoBanner() {
  const { source, exitDemo, startDemo, demoFail } = useSentinel();
  if (source !== 'demo') return null;
  return (
    <div className="demo-banner" role="note">
      <strong>DEMO SCENARIO</strong> <span>Scripted data, not live telemetry.</span>
      <button onClick={() => startDemo(demoFail)} data-cursor="Replay">Replay</button>
      <button onClick={() => startDemo(!demoFail)} data-cursor="Switch">{demoFail ? 'Run the success path' : 'Run the failure path'}</button>
      <button onClick={exitDemo} data-cursor="Exit">Exit demo</button>
    </div>
  );
}

/* ---------------- Live trace: draws only recorded readings ---------------- */
export function Trace({ readings, color, metric }: { readings: Reading[]; color: string; metric: 'err' | 'p95' }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const data = useRef(readings);
  data.current = readings;
  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext('2d')!;
    let raf = 0;
    const draw = () => {
      const dpr = Math.min(2, devicePixelRatio || 1);
      const w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const rs = data.current;
      const now = Date.now(), span = 120_000;
      ctx.strokeStyle = 'rgba(255,255,255,0.06)'; ctx.lineWidth = 1;
      for (let i = 1; i < 4; i++) { ctx.beginPath(); ctx.moveTo(0, (h * i) / 4); ctx.lineTo(w, (h * i) / 4); ctx.stroke(); }
      if (rs.length) {
        const vals = rs.map((r) => r[metric]);
        const max = Math.max(...vals) * 1.25 || 1;
        const X = (t: number) => w - ((now - t) / span) * w;
        const Y = (v: number) => h - 6 - (v / max) * (h - 14);
        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, color + '66'); grad.addColorStop(1, color + '00');
        ctx.beginPath();
        let started = false, lastX = 0, firstX = 0;
        rs.forEach((r, i) => {
          const x = X(r.t), y = Y(r[metric]);
          if (x < -10) return;
          const gap = i > 0 && r.t - rs[i - 1].t > 15_000;
          if (!started || gap) { if (started) { ctx.lineTo(lastX, h); } ctx.moveTo(x, y); if (!started) firstX = x; started = true; }
          else ctx.lineTo(x, y);
          lastX = x;
        });
        ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.shadowColor = color; ctx.shadowBlur = 12; ctx.stroke(); ctx.shadowBlur = 0;
        ctx.lineTo(lastX, h); ctx.lineTo(firstX, h); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
        const last = rs[rs.length - 1];
        const lx = X(last.t), ly = Y(last[metric]);
        ctx.beginPath(); ctx.arc(lx, ly, 4 + Math.sin(now / 200) * 1.5, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
      } else {
        ctx.fillStyle = 'rgba(255,255,255,0.35)'; ctx.font = '12px "JetBrains Mono Variable", monospace';
        ctx.fillText('No readings recorded yet', 12, h / 2);
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [color, metric]);
  return <canvas ref={ref} className="trace" aria-hidden="true" />;
}

export function OfflineCta() {
  const { startDemo } = useSentinel();
  return (
    <div className="offline-cta">
      <MagButton variant="violet" onClick={() => startDemo(false)} cursor="Play">Run the demo scenario</MagButton>
      <span className="muted">Scripted, clearly labelled, and never mixed with live data.</span>
    </div>
  );
}
