/** Live health chart: p95 latency and error rate, drawn only from readings the page has received. */
import type { Reading } from '../api/source';
import { ms, pct } from './kit';

const W = 520, H = 150;

function path(pts: [number, number][]) {
  return pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join('');
}

export function HealthChart({ readings, offline }: { readings: Reading[]; offline?: boolean }) {
  const last = readings[readings.length - 1];
  const head = (
    <div className="chart__head">
      <span className="label" style={{ margin: 0 }}>Production health · last 5 min</span>
      <div className="chart__legend">
        <span><i style={{ background: 'var(--accent)' }} />p95 {last ? ms(last.p95) : '—'}</span>
        <span><i style={{ background: 'var(--warn)' }} />errors {last ? pct(last.err) : '—'}</span>
      </div>
    </div>
  );
  if (readings.length < 2) {
    return <div className="chart" style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>{head}<div className="chart__empty">{offline ? <><b style={{ color: 'var(--ink-2)', fontWeight: 500 }}>No readings</b><span>The API is offline, so there is nothing to plot.</span></> : 'Waiting for the first readings from the health evaluator…'}</div></div>;
  }
  const t0 = readings[0].t, t1 = last.t, span = Math.max(1, t1 - t0);
  const pMax = Math.max(50, ...readings.map((r) => r.p95)) * 1.15;
  const eMax = Math.max(0.02, ...readings.map((r) => r.err)) * 1.15;
  const x = (t: number) => ((t - t0) / span) * W;
  const p = readings.map((r) => [x(r.t), H - (r.p95 / pMax) * H] as [number, number]);
  const e = readings.map((r) => [x(r.t), H - (r.err / eMax) * H] as [number, number]);
  const bad = readings.map((r, i) => (!r.healthy ? [x(r.t), x(readings[i + 1]?.t ?? r.t)] : null)).filter(Boolean) as [number, number][];
  const mins = Math.max(1, Math.round(span / 60000));
  return (
    <div className="chart">
      {head}
      <div className="chart__plot">
      <svg className="wipe" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="p95 latency and error rate over time">
        <defs>
          <linearGradient id="pf" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--accent)" stopOpacity="0.28" /><stop offset="1" stopColor="var(--accent)" stopOpacity="0" /></linearGradient>
        </defs>
        {bad.map(([a, b], i) => <rect key={i} x={a} y={0} width={Math.max(2, b - a)} height={H} fill="var(--bad)" opacity="0.08" />)}
        {[0.25, 0.5, 0.75].map((f) => <line key={f} className="grid-l" x1={0} x2={W} y1={H * f} y2={H * f} />)}
        <path d={`${path(p)}L${W},${H}L0,${H}Z`} fill="url(#pf)" />
        <path d={path(p)} fill="none" stroke="var(--accent)" strokeWidth="2" style={{ filter: 'drop-shadow(0 0 5px rgba(143,162,255,.7))' }} vectorEffect="non-scaling-stroke" />
        <path d={path(e)} fill="none" stroke="var(--warn)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" opacity="0.85" />
      </svg>
      <div className="chart__live" style={{ top: `${(p[p.length - 1][1] / H) * 100}%` }} />
      <div className="chart__scan" />
      </div>
      <div className="chart__axis"><span>{mins} min ago</span><span>now</span></div>
    </div>
  );
}
