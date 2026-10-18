import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
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
import { ClickWaves, Cursor, MagButton } from './ui/fx';
import { Boot, DemoBanner, TopBar } from './ui/hud';
import { PAGES, Palette } from './ui/palette';

gsap.registerPlugin(ScrollTrigger);
const Scene = lazy(() => import('./three/Scene').then((m) => ({ default: m.Scene })));

const LOUD: Partial<Record<SceneMode, number>> = { breach: 2.2, failed: 2, recovered: 2, contained: 1.2, investigating: 1, verifying: 1, redeploying: 1, canary: 0.8 };
let lenis: Lenis | null = null;

function useSmoothScroll(ready: boolean) {
  useEffect(() => {
    if (!ready) return;
    lenis = bus.reducedMotion ? null : new Lenis({ lerp: 0.085, smoothWheel: true, wheelMultiplier: 0.9 });
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      bus.scroll = max > 0 ? scrollY / max : 0;
      ScrollTrigger.update();
    };
    lenis?.on('scroll', onScroll);
    addEventListener('scroll', onScroll, { passive: true });
    const raf = (t: number) => lenis?.raf(t * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);
    // In-page buttons use scrollIntoView; route them through Lenis for a smooth glide.
    const orig = Element.prototype.scrollIntoView;
    const l = lenis;
    if (l) Element.prototype.scrollIntoView = function (arg?: boolean | ScrollIntoViewOptions) {
      const center = typeof arg === 'object' && arg?.block === 'center';
      l.scrollTo(this as HTMLElement, { duration: 1.6, offset: center ? -innerHeight / 2.5 : -80 });
    };
    return () => { gsap.ticker.remove(raf); l?.destroy(); lenis = null; removeEventListener('scroll', onScroll); Element.prototype.scrollIntoView = orig; };
  }, [ready]);
}

function useScrollAnimations(ready: boolean, key: string) {
  useEffect(() => {
    if (!ready) return;
    const ctx = gsap.context(() => {
      if (!bus.reducedMotion) {
        ScrollTrigger.batch('[data-reveal]', {
          start: 'top 92%',
          onEnter: (els) => gsap.fromTo(els, { y: 70, opacity: 0, rotateX: -28, filter: 'blur(10px)' }, { y: 0, opacity: 1, rotateX: 0, filter: 'blur(0px)', duration: 1.1, stagger: 0.06, ease: 'expo.out', overwrite: true, clearProps: 'filter' }),
        });
        gsap.utils.toArray<HTMLElement>('.stampcard').forEach((el, i) => {
          gsap.fromTo(el.querySelector('[data-stamp]'), { scale: 3, rotate: -18, opacity: 0 }, {
            scale: 1, rotate: -6, opacity: 1, duration: 0.5, delay: i * 0.12, ease: 'back.out(3)',
            scrollTrigger: { trigger: el, start: 'top 88%' }, onComplete: () => bus.pulse(0.5),
          });
        });
        if (document.querySelector('.sec--outcome')) gsap.fromTo('.outcome__word', { letterSpacing: '0.6em', scale: 0.7 }, { letterSpacing: '-0.04em', scale: 1, ease: 'none', scrollTrigger: { trigger: '.sec--outcome', start: 'top bottom', end: 'center center', scrub: 1 } });
        if (document.querySelector('.end')) gsap.fromTo('.end__big', { scale: 0.85, opacity: 0.2 }, { scale: 1, opacity: 1, ease: 'none', scrollTrigger: { trigger: '.end', start: 'top bottom', end: 'center center', scrub: 1 } });
        if (document.querySelector('.phead__title')) gsap.to('.phead__title', { yPercent: -40, opacity: 0.25, ease: 'none', scrollTrigger: { trigger: '.phead', start: 'top top', end: 'bottom top', scrub: 0.6 } });
      }
      const mm = gsap.matchMedia();
      mm.add('(min-width: 900px) and (prefers-reduced-motion: no-preference)', () => {
        const track = document.querySelector<HTMLElement>('.loop__track');
        if (!track) return;
        const dist = () => Math.max(0, track.scrollWidth - innerWidth + 120);
        gsap.to(track, {
          x: () => -dist(), ease: 'none',
          scrollTrigger: { trigger: '.sec--loop', pin: true, start: 'top top', end: () => `+=${dist()}`, scrub: 0.8, invalidateOnRefresh: true, anticipatePin: 1 },
        });
      });
    });
    const t = setTimeout(() => ScrollTrigger.refresh(), 300);
    return () => { clearTimeout(t); ctx.revert(); };
  }, [ready, key]);
}

/** Full-screen warp between pages. */
function Warp({ label, color }: { label: string; color: string }) {
  return (
    <div className="warp" style={{ ['--c' as string]: color }} aria-hidden="true">
      <div className="warp__ring" /><div className="warp__ring warp__ring--2" />
      <p className="warp__label" data-text={label}>{label}</p>
    </div>
  );
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

  // A state change is an event: shockwave through the scene and a flash across the screen.
  const prev = useRef<SceneMode | null>(null);
  const [flash, setFlash] = useState<{ k: number; c: string } | null>(null);
  useEffect(() => {
    if (prev.current && prev.current !== mode && LOUD[mode]) {
      bus.pulse(LOUD[mode]);
      if (!bus.reducedMotion) setFlash({ k: Date.now(), c: MODE_COLOR[mode] });
    }
    prev.current = mode;
  }, [mode]);

  // Route change: jump to the top, warp, shockwave.
  const [warp, setWarp] = useState<{ k: number; label: string } | null>(null);
  const first = useRef(true);
  useEffect(() => {
    if (lenis) lenis.scrollTo(0, { immediate: true, force: true }); else scrollTo(0, 0);
    if (first.current) { first.current = false; return; }
    bus.pulse(1.6);
    const p = PAGES.find((x) => x.to === loc.pathname);
    const label = p?.label ?? (loc.pathname.startsWith('/incidents/') ? decodeURIComponent(loc.pathname.split('/')[2] ?? '') : 'Sentinel');
    if (bus.reducedMotion) return;
    setWarp({ k: Date.now(), label });
    const t = setTimeout(() => setWarp(null), 1150);
    return () => clearTimeout(t);
  }, [loc.pathname]);

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

  useSmoothScroll(booted);
  useScrollAnimations(booted, `${loc.pathname}:${d.incident?.id ?? 'none'}:${Object.keys(snap.details).length}`);

  const split = snap.status?.traffic_split;
  const ctx = useMemo(() => ({ d, now, setScene }), [d, now]);
  return (
    <Mission.Provider value={ctx}>
      <div className={`app mode-${mode}${home ? '' : ' is-sub'}`} style={{ ['--mode' as string]: MODE_COLOR[mode] }}>
        <Suspense fallback={<div className="scene-fallback" />}>
          <Scene mode={mode} stages={stages} candidatePct={split?.candidate_percent ?? 0} offsetX={wide ? (home ? 2.6 : 3.3) : 0} narrow={!wide} />
        </Suspense>
        <div className="grain" aria-hidden="true" />
        {flash && <div key={flash.k} className="flash" style={{ ['--c' as string]: flash.c }} aria-hidden="true" onAnimationEnd={() => setFlash(null)} />}
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
        {warp && <Warp key={warp.k} label={warp.label} color={MODE_COLOR[mode]} />}
        <Palette open={palette} onClose={() => setPalette(false)} />
        <ClickWaves />
        <Cursor />
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
