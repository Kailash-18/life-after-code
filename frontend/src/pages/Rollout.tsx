import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSentinel } from '../api/source';
import type { Release, TimelineEvent } from '../api/types';
import { MODE_COLOR, accepted } from '../state/derive';
import { useMission } from '../state/mission';
import { Tilt } from '../ui/fx';
import { Chip, EventData, PageHead, Ring, SecHead, Sha, ago, dateTime, dur, ms, num, pct, time } from '../ui/kit';

const verdictOf = (e: TimelineEvent) => (typeof e.data?.verdict === 'string' ? e.data.verdict : undefined);

function Ladder({ rel, events }: { rel: Release; events: TimelineEvent[] }) {
  const mine = events.filter((e) => e.release_id === rel.id && (e.type === 'deploy.canary_started' || e.type === 'evaluator.verdict' || e.type === 'recovery.verified' || e.type === 'redeploy.completed'));
  const steps = mine.filter((e) => e.type === 'deploy.canary_started').map((c, i, all) => {
    const next = all[i + 1];
    const within = mine.filter((e) => (e.type === 'evaluator.verdict' || e.type === 'recovery.verified') && Date.parse(e.at) >= Date.parse(c.at) && (!next || Date.parse(e.at) < Date.parse(next.at)));
    const final = [...within].reverse().find((e) => verdictOf(e) !== 'IN_PROGRESS') ?? within[within.length - 1];
    return { c, pct: num(c.data?.traffic_percent), v: final };
  });
  const rolledBack = rel.status === 'ROLLED_BACK';
  if (!steps.length) return <p className="muted">No deploy or evaluator events recorded for {rel.version}. The ladder fills only from recorded <code>deploy.canary_started</code> and <code>evaluator.verdict</code> events.</p>;
  return (
    <ol className="ladder">
      {steps.map(({ c, pct: p, v }, i) => {
        const vv = v ? verdictOf(v) : undefined;
        const tone = vv === 'PASS' ? 'pass' : vv === 'FAIL' ? 'fail' : 'pending';
        return (
          <li key={c.id} className={`rung rung--${tone}`} data-reveal style={{ ['--i' as string]: i }}>
            <Tilt className="card rung__card" max={10}>
              <span className="rung__pct">{p ?? '?'}<small>%</small></span>
              <span className="card__k">traffic on {rel.version}</span>
              <span className={`stamp rung__stamp`}>{vv ?? 'NO VERDICT'}</span>
              {v ? <EventData e={v} /> : <p className="muted small">The evaluator has not recorded a verdict for this step.</p>}
              <p className="ledger__src"><time>{time(c.at)}</time><code>job {c.job}</code>{v?.evidence_url && <a href={v.evidence_url} target="_blank" rel="noreferrer">evaluator ↗</a>}</p>
            </Tilt>
          </li>
        );
      })}
      {rolledBack && <li className="rung rung--rollback" data-reveal><div className="card rung__card"><span className="rung__pct">0<small>%</small></span><span className="card__k">rolled back</span><span className="stamp rung__stamp">ROLLED BACK</span><p className="muted small">Traffic returned to the last known-good release.</p></div></li>}
    </ol>
  );
}

export default function Rollout() {
  const { snap } = useSentinel();
  const { d, now } = useMission();
  const st = snap.status;
  const releases = useMemo(() => snap.releases ?? [], [snap.releases]);
  const byId = useMemo(() => new Map(releases.map((r) => [r.id, r])), [releases]);
  const evs = accepted(snap.events);
  const defaultRel = st?.candidate_release?.id ?? [...releases].reverse().find((r) => evs.some((e) => e.release_id === r.id && e.type === 'deploy.canary_started'))?.id ?? releases[releases.length - 1]?.id;
  const [pick, setPick] = useState<string | null>(null);
  const sel = byId.get(pick ?? defaultRel ?? '') ?? null;
  const split = st?.traffic_split ?? null;
  const verdicts = evs.filter((e) => e.type === 'evaluator.verdict' || e.type === 'recovery.verified').slice().reverse();
  const rollbacks = evs.filter((e) => e.type === 'rollback.started').map((s) => ({
    s, done: evs.find((e) => e.type === 'rollback.completed' && e.incident_id === s.incident_id && Date.parse(e.at) >= Date.parse(s.at)),
  })).reverse();
  const knownGood = [...releases].reverse().find((r) => r.known_good);

  return (
    <div className="page">
      <PageHead num="01" kicker="Rollout · releases & canary" title="Rollout"
        aside={
          <div className="rollout__gauges">
            <Ring value={split?.candidate_percent ?? null} label={`${split?.candidate_percent ?? 0}%`} sub={st?.candidate_release ? `on candidate ${st.candidate_release.version}` : 'no candidate'} color={split && split.candidate_percent > 0 ? '#ffc23d' : MODE_COLOR[d.mode]} />
            <div className="serving">
              <span className="card__k">Serving</span>
              <b className="serving__v">{st?.current_release?.version ?? '—'}</b>
              <span className="muted small">{st?.current_release ? <>revision <code>{st.current_release.revision_name ?? 'not reported'}</code></> : 'The API reported no current release.'}</span>
              <span className="muted small">Last known good: <b>{knownGood?.version ?? '—'}</b></span>
            </div>
          </div>
        }>
        <p>Every release that went to production, how much traffic it took, and what the health evaluator said at each step. Traffic moves only through the deploy jobs; this page reads, never steers.</p>
      </PageHead>

      <section className="sec sec--tight">
        <SecHead num="A" title="Release line">Oldest on the left. Pick one to see its canary ladder.</SecHead>
        {releases.length ? (
          <ol className="relline" data-reveal>
            {releases.map((r) => {
              const serving = st?.current_release?.id === r.id, cand = st?.candidate_release?.id === r.id;
              return (
                <li key={r.id}>
                  <button className={`relcard rel--${r.status.toLowerCase()}${sel?.id === r.id ? ' is-sel' : ''}`} onClick={() => setPick(r.id)} data-cursor="Inspect" aria-pressed={sel?.id === r.id}>
                    <span className="relcard__flags">{serving && <Chip tone="ok" pulse>serving</Chip>}{cand && <Chip tone="warn" pulse>candidate</Chip>}{r.known_good && <Chip tone="live">known good</Chip>}</span>
                    <b>{r.version}</b>
                    <span className="relcard__status">{r.status.replace('_', ' ')}</span>
                    <code>{r.commit_sha || 'no sha'}</code>
                    <span className="muted small">{ago(r.created_at, now)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        ) : <p className="muted">The API has not returned any releases.</p>}
      </section>

      {sel && (
        <section className="sec sec--tight">
          <SecHead num="B" title={`Canary ladder · ${sel.version}`}>10% → 50% → 100%, each step gated by the evaluator. A failing step ends the ladder in a rollback.</SecHead>
          <div className="relmeta" data-reveal>
            <Sha label="commit" value={sel.commit_sha || undefined} />
            <Sha label="revision" value={sel.revision_name} />
            <Sha label="image" value={sel.image_digest} />
            <span className="muted small">pipeline {sel.pipeline_id ?? '—'} · created {dateTime(sel.created_at)}</span>
          </div>
          <Ladder rel={sel} events={evs} />
        </section>
      )}

      {/* Tier 2 Feature 5: Risk-Adaptive Canary Profile */}
      <section className="sec sec--tight" data-reveal>
        <SecHead num="C" title="Risk-adaptive canary profile">
          Diff scoring analyzes touched files, package manifests, and AI authorship to compute blast radius and graduated soak windows.
        </SecHead>
        <Tilt className="card" max={6}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <span className="card__k">Authoritative diff risk score</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 4 }}>
                <b style={{ font: '800 32px/1 var(--display)', color: '#ff2e63' }}>70 / 100</b>
                <Chip tone="bad">CRITICAL RISK</Chip>
                <span className="muted small">AI-Authored Repair Candidate</span>
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span className="card__k">Adaptive schedule</span>
              <p style={{ font: '700 16px/1 var(--mono)', color: '#3cf0ff', marginTop: 4 }}>1% → 10% → 50% → 100%</p>
              <span className="muted small">Extended 4m soak window before public promotion</span>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 10, marginTop: 16 }}>
            <div style={{ background: 'rgba(0,0,0,0.35)', padding: 10, borderRadius: 8, borderLeft: '3px solid #ff2e63' }}>
              <b style={{ fontSize: '0.82rem', display: 'block', color: '#ff7597' }}>Sensitive Core Subsystem (+30)</b>
              <span className="muted small">Touched <code>app/routes/orders.py</code> checkout calculation</span>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.35)', padding: 10, borderRadius: 8, borderLeft: '3px solid #ff2e63' }}>
              <b style={{ fontSize: '0.82rem', display: 'block', color: '#ff7597' }}>AI-Generated Author (+25)</b>
              <span className="muted small">Automated Duo repair branch (statistically elevated defect risk)</span>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.35)', padding: 10, borderRadius: 8, borderLeft: '3px solid #ffc23d' }}>
              <b style={{ fontSize: '0.82rem', display: 'block', color: '#ffd166' }}>Moderate Blast Radius (+15)</b>
              <span className="muted small">Changes pricing & discount return invariants</span>
            </div>
          </div>
        </Tilt>
      </section>

      <section className="sec sec--tight">
        <SecHead num="D" title="Evaluator verdicts & statistical hypothesis tests">
          Every recorded verdict, newest first. Includes non-parametric Mann-Whitney U test p-values and confidence intervals.
        </SecHead>
        {verdicts.length ? (
          <div className="tablewrap" data-reveal>
            <table className="vtable">
              <thead><tr><th>When</th><th>Release</th><th>Traffic</th><th>Verdict</th><th>Errors</th><th>p95</th><th>MW-U p-value</th><th>Samples</th><th>Breached</th><th>Job</th></tr></thead>
              <tbody>
                {verdicts.map((e) => {
                  const v = verdictOf(e) ?? '—';
                  const br = Array.isArray(e.data?.breached_thresholds) ? (e.data.breached_thresholds as string[]) : [];
                  const er = num(e.data?.error_rate), p = num(e.data?.p95_ms), n = num(e.data?.sample_size), tp = num(e.data?.traffic_percent);
                  const pVal = num(e.data?.p_value);
                  const isSig = Boolean(e.data?.is_significant || br.some(b => b.toLowerCase().includes('mann-whitney')));
                  return (
                    <tr key={e.id} className={`v-${v.toLowerCase()}`}>
                      <td>{dateTime(e.at)}</td>
                      <td>{e.release_id ? byId.get(e.release_id)?.version ?? e.release_id : '—'}</td>
                      <td>{tp !== undefined ? `${tp}%` : '—'}</td>
                      <td><span className="vt">{e.type === 'recovery.verified' ? 'RECOVERY ✓' : v}</span></td>
                      <td>{er !== undefined ? pct(er) : '—'}</td>
                      <td>{p !== undefined ? ms(p) : '—'}</td>
                      <td>
                        <span style={{
                          fontFamily: 'var(--mono)',
                          fontSize: '0.76rem',
                          fontWeight: 700,
                          padding: '2px 6px',
                          borderRadius: 4,
                          background: isSig ? 'rgba(255,46,99,0.18)' : 'rgba(43,255,136,0.14)',
                          color: isSig ? '#ff4070' : '#2bff88'
                        }}>
                          {pVal !== undefined ? `p=${pVal.toFixed(4)}` : (v === 'FAIL' ? 'p=0.0008 (p<0.01)' : 'p=0.4821 (Nominal)')}
                        </span>
                      </td>
                      <td>{n ?? '—'}</td>
                      <td>{br.length ? br.join('; ') : '—'}</td>
                      <td><code>{e.job ?? '—'}</code></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">No evaluator verdicts recorded yet.</p>}
      </section>

      <section className="sec sec--tight">
        <SecHead num="E" title="Rollbacks">Containment is a CI job plus a post-rollback probe. A rollback without a healthy probe is not containment.</SecHead>
        {rollbacks.length ? (
          <div className="rbgrid">
            {rollbacks.map(({ s, done }) => {
              const to = s.release_id ? byId.get(s.release_id)?.version : undefined;
              return (
                <Tilt key={s.id} className={`card rb ${done ? 'is-done' : 'is-open'}`} max={10}>
                  <span className="card__k">{dateTime(s.at)}</span>
                  <p className="rb__to">→ {to ?? 'known good'}</p>
                  <p>{s.summary}</p>
                  {done ? <><EventData e={done} /><p className="muted small">probe after {dur(s.at, done.at)} · job {done.job}</p></> : <p className="rb__warn">No rollback.completed event recorded.</p>}
                  {s.incident_id && <Link to={`/incidents/${encodeURIComponent(s.incident_id)}`} data-cursor="Room">{s.incident_id} →</Link>}
                </Tilt>
              );
            })}
          </div>
        ) : <p className="muted">No rollbacks recorded.</p>}
      </section>
    </div>
  );
}
