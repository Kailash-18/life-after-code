import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { HashRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { SentinelProvider, useSentinel } from './api/source';
import Gates from './pages/Gates';
import Home from './pages/Home';
import IncidentRoom from './pages/IncidentRoom';
import Incidents from './pages/Incidents';
import Ledger from './pages/Ledger';
import Rollout from './pages/Rollout';
import System from './pages/System';
import { bus } from './state/bus';
import { derive, MODE_COLOR, type SceneMode } from './state/derive';
import { Mission, type SceneOverride } from './state/mission';
import { MagButton } from './ui/fx';
import { Boot, DemoBanner, TopBar } from './ui/hud';
import { PAGES, Palette } from './ui/palette';

gsap.registerPlugin(ScrollTrigger);
const Scene = lazy(() => import('./three/Scene').then((m) => ({ default: m.Scene })));

/** A state change still registers in the core, but as a short, soft pulse. */
const PULSE: Partial<Record<SceneMode, number>> = { breach: 0.8, failed: 0.7, recovered: 0.6 };

/** Native scrolling; the scene only reads how far down the page you are. */
function useScrollProgress() {
  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      bus.scroll = max > 0 ? scrollY / max : 0;
    };
    onScroll();
    addEventListener('scroll', onScroll, { passive: true });
    return () => removeEventListener('scroll', onScroll);
  }, []);
}

/** One gentle fade-up per element, the first time it scrolls into view. */
function useReveals(ready: boolean, key: string) {
  useEffect(() => {
    if (!ready || bus.reducedMotion) return;
    const ctx = gsap.context(() => {
      ScrollTrigger.batch('[data-reveal]', {
        start: 'top 94%',
        once: true,
        onEnter: (els) => gsap.fromTo(els, { y: 14, opacity: 0 }, { y: 0, opacity: 1, duration: 0.45, stagger: 0.03, ease: 'power2.out', overwrite: true }),
      });
    });
    const t = setTimeout(() => ScrollTrigger.refresh(), 200);
    return () => { clearTimeout(t); ctx.revert(); };
  }, [ready, key]);
}

function NotFound() {
  const nav = useNavigate();
  return (
    <div className="page"><header className="phead"><div className="phead__k"><span className="phead__num">404</span><span>No such console</span></div>
      <h1 className="phead__title">Lost signal</h1>
      <div className="phead__sub"><MagButton onClick={() => nav('/')} cursor="Home">Back to Mission Control</MagButton></div></header></div>
  );
}

function Shell() {
  const { snap, connected } = useSentinel();
  const loc = useLocation();
  const nav = useNavigate();
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const d = useMemo(() => derive(snap, connected, now), [snap, connected, now]);
  const [scene, setScene] = useState<SceneOverride | null>(null);
  const [booted, setBooted] = useState(false);
  const onBoot = useCallback(() => setBooted(true), []);
  const [palette, setPalette] = useState(false);
  const [wide, setWide] = useState(() => innerWidth > 900);
  useEffect(() => { const r = () => setWide(innerWidth > 900); addEventListener('resize', r); return () => removeEventListener('resize', r); }, []);

  const mode = scene?.mode ?? d.mode;
  const stages = scene?.stages ?? d.stages;
  const home = loc.pathname === '/';

  const prev = useRef<SceneMode | null>(null);
  useEffect(() => {
    if (prev.current && prev.current !== mode && PULSE[mode]) bus.pulse(PULSE[mode]);
    prev.current = mode;
  }, [mode]);

  // Route change: start the new page at the top.
  useEffect(() => { scrollTo(0, 0); }, [loc.pathname]);

  // Keys: ⌘K / Ctrl+K / "/" opens the palette; 1–6 jump between consoles.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target as HTMLElement)?.tagName ?? '');
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette((x) => !x); return; }
      if (typing || palette || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === '/') { e.preventDefault(); setPalette(true); }
      const n = Number(e.key);
      if (n >= 1 && n <= PAGES.length) nav(PAGES[n - 1].to);
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, [palette, nav]);

  useScrollProgress();
  useReveals(booted, `${loc.pathname}:${d.incident?.id ?? 'none'}:${Object.keys(snap.details).length}`);

  const split = snap.status?.traffic_split;
  const ctx = useMemo(() => ({ d, now, setScene }), [d, now]);
  return (
    <Mission.Provider value={ctx}>
      <div className={`app mode-${mode}${home ? '' : ' is-sub'}`} style={{ ['--mode' as string]: MODE_COLOR[mode] }}>
        <Suspense fallback={<div className="scene-fallback" />}>
          <Scene mode={mode} stages={stages} candidatePct={split?.candidate_percent ?? 0} offsetX={wide ? (home ? 2.6 : 3.3) : 0} narrow={!wide} />
        </Suspense>
        <div className="grain" aria-hidden="true" />
        <DemoBanner />
        <TopBar mode={mode} onMenu={() => setPalette(true)} />
        <main className={`content${booted ? ' is-in' : ''}`}>
          <div key={loc.pathname} className="route">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/rollout" element={<Rollout />} />
              <Route path="/incidents" element={<Incidents />} />
              <Route path="/incidents/:id" element={<IncidentRoom />} />
              <Route path="/gates" element={<Gates />} />
              <Route path="/ledger" element={<Ledger />} />
              <Route path="/system" element={<System />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </div>
        </main>
        <Palette open={palette} onClose={() => setPalette(false)} />
        {!booted && <Boot onDone={onBoot} />}
        <p className="sr-only" role="status" aria-live="polite">{d.headline}</p>
      </div>
    </Mission.Provider>
  );
}

export default function App() {
  return (
    <SentinelProvider>
      <HashRouter>
        <Shell />
      </HashRouter>
    </SentinelProvider>
  );
}
