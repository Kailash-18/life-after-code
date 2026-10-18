import { useEffect, useRef, useState, type ElementType, type MouseEvent as RMouseEvent, type ReactNode } from 'react';
import { bus } from '../state/bus';

const GLYPHS = '!<>-_\\/[]{}—=+*^?#01ABCDEFXYZ▲▼◆●';
const finePointer = () => typeof matchMedia === 'function' && matchMedia('(pointer: fine)').matches;

/* ---------------- Custom cursor ---------------- */
export function Cursor() {
  const dot = useRef<HTMLDivElement>(null);
  const ring = useRef<HTMLDivElement>(null);
  const [label, setLabel] = useState('');
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!finePointer()) return;
    setOn(true);
    document.documentElement.classList.add('has-cursor');
    let x = innerWidth / 2, y = innerHeight / 2, rx = x, ry = y, raf = 0, hot = false, down = false;
    const move = (e: PointerEvent) => {
      x = e.clientX; y = e.clientY;
      bus.pointer.x = (x / innerWidth) * 2 - 1; bus.pointer.y = -((y / innerHeight) * 2 - 1);
      const el = (e.target as HTMLElement | null)?.closest('a, button, [data-cursor]') as HTMLElement | null;
      hot = !!el;
      setLabel(el?.dataset.cursor ?? '');
    };
    const dn = () => { down = true; }, up = () => { down = false; };
    const loop = () => {
      rx += (x - rx) * 0.18; ry += (y - ry) * 0.18;
      if (dot.current) dot.current.style.transform = `translate3d(${x}px,${y}px,0)`;
      if (ring.current) ring.current.style.transform = `translate3d(${rx}px,${ry}px,0) scale(${(hot ? 1.9 : 1) * (down ? 0.75 : 1)})`;
      raf = requestAnimationFrame(loop);
    };
    addEventListener('pointermove', move); addEventListener('pointerdown', dn); addEventListener('pointerup', up);
    raf = requestAnimationFrame(loop);
    return () => { removeEventListener('pointermove', move); removeEventListener('pointerdown', dn); removeEventListener('pointerup', up); cancelAnimationFrame(raf); document.documentElement.classList.remove('has-cursor'); };
  }, []);
  if (!on) return null;
  return (
    <>
      <div ref={ring} className="cursor-ring" aria-hidden="true"><span>{label}</span></div>
      <div ref={dot} className="cursor-dot" aria-hidden="true" />
    </>
  );
}

/* ---------------- Global click shockwave ---------------- */
export function ClickWaves() {
  const [waves, setWaves] = useState<{ id: number; x: number; y: number }[]>([]);
  useEffect(() => {
    let id = 0;
    const onDown = (e: PointerEvent) => {
      const n = ++id;
      setWaves((w) => [...w.slice(-5), { id: n, x: e.clientX, y: e.clientY }]);
      setTimeout(() => setWaves((w) => w.filter((v) => v.id !== n)), 900);
      bus.pulse(0.45);
    };
    addEventListener('pointerdown', onDown);
    return () => removeEventListener('pointerdown', onDown);
  }, []);
  return (
    <div className="waves" aria-hidden="true">
      {waves.map((w) => <span key={w.id} className="wave" style={{ left: w.x, top: w.y }} />)}
    </div>
  );
}

/* ---------------- Particle burst ---------------- */
function burst(x: number, y: number, color: string, n = 26) {
  const host = document.body;
  for (let i = 0; i < n; i++) {
    const p = document.createElement('i');
    p.className = 'spark';
    const a = (Math.PI * 2 * i) / n + Math.random() * 0.4;
    const d = 60 + Math.random() * 110;
    p.style.left = `${x}px`; p.style.top = `${y}px`;
    p.style.setProperty('--dx', `${Math.cos(a) * d}px`);
    p.style.setProperty('--dy', `${Math.sin(a) * d}px`);
    p.style.setProperty('--c', color);
    p.style.setProperty('--r', `${Math.random() * 720 - 360}deg`);
    host.appendChild(p);
    setTimeout(() => p.remove(), 900);
  }
}

/* ---------------- Magnetic, exploding button ---------------- */
export function MagButton({
  children, onClick, href, variant = 'primary', cursor = 'Go', className = '', disabled, type = 'button', ariaLabel,
}: {
  children: ReactNode; onClick?: () => void; href?: string; variant?: 'primary' | 'ghost' | 'danger' | 'violet' | 'green';
  cursor?: string; className?: string; disabled?: boolean; type?: 'button' | 'submit'; ariaLabel?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const inner = useRef<HTMLSpanElement>(null);
  const move = (e: RMouseEvent) => {
    const el = ref.current;
    if (!el || !finePointer()) return;
    const r = el.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    el.style.transform = `translate(${dx * 0.28}px, ${dy * 0.38}px) rotateX(${-dy * 0.25}deg) rotateY(${dx * 0.12}deg)`;
    if (inner.current) inner.current.style.transform = `translate(${dx * 0.14}px, ${dy * 0.18}px)`;
    el.style.setProperty('--mx', `${e.clientX - r.left}px`);
    el.style.setProperty('--my', `${e.clientY - r.top}px`);
  };
  const leave = () => {
    if (ref.current) ref.current.style.transform = '';
    if (inner.current) inner.current.style.transform = '';
  };
  const click = (e: RMouseEvent) => {
    const color = getComputedStyle(ref.current!).getPropertyValue('--accent').trim() || '#3cf0ff';
    if (!bus.reducedMotion) burst(e.clientX, e.clientY, color);
    bus.pulse(1.2);
    ref.current?.classList.remove('is-hit'); void ref.current?.offsetWidth; ref.current?.classList.add('is-hit');
    onClick?.();
  };
  const Tag = (href ? 'a' : 'button') as ElementType;
  return (
    <Tag
      ref={ref}
      className={`mag mag--${variant} ${className}`}
      href={href}
      type={href ? undefined : type}
      disabled={disabled}
      aria-label={ariaLabel}
      data-cursor={cursor}
      onMouseMove={move}
      onMouseLeave={leave}
      onClick={click}
    >
      <span className="mag__glow" aria-hidden="true" />
      <span className="mag__inner" ref={inner}>{children}</span>
    </Tag>
  );
}

/* ---------------- Text that decodes itself ---------------- */
export function Scramble({ text, as: Tag = 'span', className, delay = 0, speed = 1 }: { text: string; as?: ElementType; className?: string; delay?: number; speed?: number }) {
  const [out, setOut] = useState(text);
  const ref = useRef<HTMLElement>(null);
  const prev = useRef('');
  useEffect(() => {
    if (bus.reducedMotion) { setOut(text); return; }
    let raf = 0, start = 0, started = false;
    const from = prev.current;
    prev.current = text;
    const run = (t: number) => {
      if (!start) start = t + delay;
      const p = Math.max(0, (t - start) / (650 + text.length * 22 / speed));
      let s = '';
      for (let i = 0; i < text.length; i++) {
        const reveal = i / text.length < p * 1.15;
        s += reveal || text[i] === ' ' ? text[i] : GLYPHS[(Math.random() * GLYPHS.length) | 0];
      }
      setOut(s);
      if (p < 1) raf = requestAnimationFrame(run); else setOut(text);
    };
    const go = () => { if (!started) { started = true; raf = requestAnimationFrame(run); } };
    const el = ref.current;
    if (!el || from) { go(); return () => cancelAnimationFrame(raf); }
    const io = new IntersectionObserver((es) => { if (es.some((x) => x.isIntersecting)) { go(); io.disconnect(); } }, { threshold: 0.2 });
    io.observe(el);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [text, delay, speed]);
  return <Tag ref={ref} className={className} aria-label={text}><span aria-hidden="true">{out}</span></Tag>;
}

/* ---------------- 3D tilt card with glare ---------------- */
export function Tilt({ children, className = '', max = 10, as: Tag = 'div' }: { children: ReactNode; className?: string; max?: number; as?: ElementType }) {
  const ref = useRef<HTMLElement>(null);
  const move = (e: RMouseEvent) => {
    const el = ref.current;
    if (!el || !finePointer()) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    el.style.transform = `perspective(900px) rotateX(${(0.5 - py) * max}deg) rotateY(${(px - 0.5) * max}deg) translateZ(0)`;
    el.style.setProperty('--gx', `${px * 100}%`);
    el.style.setProperty('--gy', `${py * 100}%`);
  };
  const leave = () => { if (ref.current) ref.current.style.transform = ''; };
  return <Tag ref={ref} className={`tilt ${className}`} onMouseMove={move} onMouseLeave={leave}>{children}<span className="tilt__glare" aria-hidden="true" /></Tag>;
}

/* ---------------- Number that counts to its value ---------------- */
export function Count({ value, format }: { value: number; format: (v: number) => string }) {
  const [v, setV] = useState(value);
  const cur = useRef(value);
  useEffect(() => {
    if (bus.reducedMotion) { cur.current = value; setV(value); return; }
    const from = cur.current; let raf = 0; const t0 = performance.now();
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / 700);
      const e = 1 - Math.pow(1 - p, 3);
      cur.current = from + (value - from) * e;
      setV(cur.current);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <>{format(v)}</>;
}

/* ---------------- Big kinetic title: every letter is alive ---------------- */
export function KineticTitle({ text }: { text: string }) {
  return (
    <h1 className="kinetic" aria-label={text}>
      {[...text].map((c, i) => (
        <span key={i} className="kinetic__ch" style={{ ['--i' as string]: i }} aria-hidden="true"
          onMouseEnter={(e) => { const el = e.currentTarget; el.classList.remove('is-pop'); void el.offsetWidth; el.classList.add('is-pop'); }}>
          {c}
        </span>
      ))}
    </h1>
  );
}
