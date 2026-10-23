/**
 * Small interface primitives. Motion is deliberately restrained: hover changes colour and
 * border only, numbers ease to their value, and nothing moves on its own except live state.
 */
import { useEffect, useRef, useState, type ElementType, type ReactNode } from 'react';
import { bus } from '../state/bus';

/* ---------------- Button ---------------- */
export function MagButton({
  children, onClick, href, variant = 'primary', className = '', disabled, type = 'button', ariaLabel,
}: {
  children: ReactNode; onClick?: () => void; href?: string; variant?: 'primary' | 'ghost' | 'danger' | 'violet' | 'green';
  /** kept for call-site compatibility; there is no custom cursor any more */
  cursor?: string; className?: string; disabled?: boolean; type?: 'button' | 'submit'; ariaLabel?: string;
}) {
  const Tag = (href ? 'a' : 'button') as ElementType;
  return (
    <Tag className={`mag mag--${variant} ${className}`} href={href} type={href ? undefined : type} disabled={disabled} aria-label={ariaLabel} onClick={onClick}>
      <span className="mag__inner">{children}</span>
    </Tag>
  );
}

/* ---------------- Text (previously decoded itself; now rendered as is) ---------------- */
export function Scramble({ text, as: Tag = 'span', className }: { text: string; as?: ElementType; className?: string; delay?: number; speed?: number }) {
  return <Tag className={className}>{text}</Tag>;
}

/* ---------------- Card wrapper (flat; the class name is kept for styling) ---------------- */
export function Tilt({ children, className = '', as: Tag = 'div' }: { children: ReactNode; className?: string; max?: number; as?: ElementType }) {
  return <Tag className={`tilt ${className}`}>{children}</Tag>;
}

/* ---------------- Number that eases to its value ---------------- */
export function Count({ value, format }: { value: number; format: (v: number) => string }) {
  const [v, setV] = useState(value);
  const cur = useRef(value);
  useEffect(() => {
    if (bus.reducedMotion) { cur.current = value; setV(value); return; }
    const from = cur.current; let raf = 0; const t0 = performance.now();
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / 400);
      cur.current = from + (value - from) * (1 - Math.pow(1 - p, 3));
      setV(cur.current);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <>{format(v)}</>;
}

/* ---------------- Big title: letters rise once on load ---------------- */
export function KineticTitle({ text }: { text: string }) {
  return (
    <h1 className="kinetic" aria-label={text}>
      {[...text].map((c, i) => <span key={i} className="kinetic__ch" style={{ ['--i' as string]: i }} aria-hidden="true">{c}</span>)}
    </h1>
  );
}
