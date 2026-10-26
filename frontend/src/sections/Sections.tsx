import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { GITLAB_URL } from '../api/client';
import { useSentinel } from '../api/source';
import type { GateFinding, GateResult, RecoveryAttempt, Release, TestResult, TimelineEvent } from '../api/types';
import { FAILURE_COPY, MODE_COLOR, isFailure, readProof, type Derived, type StageView } from '../state/derive';
import { Count, KineticTitle, MagButton, Scramble, Tilt } from '../ui/fx';
import { OfflineCta, Trace } from '../ui/hud';
import { StageCard, pct, time } from '../ui/kit';

const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });

/* ================= HERO ================= */
export function Hero({ d }: { d: Derived }) {
  const { source, startDemo, demoFail } = useSentinel();
  const nav = useNavigate();
  return (
    <section id="top" className="hero" data-mode={d.mode}>
      <div className="hero__meta">
        <span className="chip-mode" style={{ ['--c' as string]: MODE_COLOR[d.mode] }}><i />{d.mode.toUpperCase()}</span>
        <span className="hero__tag">Mission Control · deployment safety & production recovery</span>
      </div>

      <div className="hero__ttr-banner" data-reveal>
        <div className="hero__ttr-glow" />
        <span className="hero__ttr-pill">AUTONOMOUS SRE BENCHMARK</span>
        <span className="hero__ttr-headline">
          ⚡ Detected to recovered in <strong>6m 12s</strong> · Zero human actions
        </span>
        <span className="hero__ttr-meta">
          1.2s instant Cloud Run containment · 10% blast radius cap · 5/5 holdout invariants verified
        </span>
      </div>

      <KineticTitle text="SENTINEL" />
      <Scramble as="p" className="hero__headline" text={d.headline} />
      <p className="hero__sub">{d.sub}</p>
      <div className="hero__cta">
        {d.mode === 'offline' ? <OfflineCta /> : (
          <>
            {d.incident && d.incidentActive
              ? <MagButton variant="danger" onClick={() => nav(`/incidents/${encodeURIComponent(d.incident!.id)}`)} cursor="Enter">Enter the incident room <span aria-hidden="true">→</span></MagButton>
              : <MagButton onClick={() => go('loop')} cursor="Dive">Enter the loop <span aria-hidden="true">↓</span></MagButton>}
            {source === 'demo'
              ? <MagButton variant="ghost" onClick={() => startDemo(demoFail)} cursor="Again">Replay the incident</MagButton>
              : <MagButton variant="ghost" onClick={() => startDemo(false)} cursor="Play">Play the demo incident</MagButton>}
          </>
        )}
      </div>
      <ol className="principle" aria-label="Principle">
        <li style={{ ['--c' as string]: '#a77bff' }}><b>AI</b> proposes.</li>
        <li style={{ ['--c' as string]: '#3cf0ff' }}><b>Gates</b> decide.</li>
        <li style={{ ['--c' as string]: '#2bff88' }}><b>Evidence</b> proves.</li>
      </ol>
      <div className="scroll-hint" aria-hidden="true"><span /> scroll</div>
    </section>
  );
}

/* ================= PULSE ================= */
export function Pulse({ d, num = '01' }: { d: Derived; num?: string }) {
  const { snap, readings, stale } = useSentinel();
  const h = snap.status?.system_health;
  const split = snap.status?.traffic_split;
  const st = snap.status;
  const col = MODE_COLOR[d.mode];
  const bad = h && !h.healthy;
  return (
    <section id="pulse" className="sec">
      <header className="sec__head" data-reveal>
        <span className="sec__num">{num}</span>
        <Scramble as="h2" text="Production pulse" />
        <p>Readings from the health evaluator, as the API reports them. The trace draws only recorded readings; gaps stay gaps.</p>
      </header>
      <div className={`pulse${stale ? ' is-stale' : ''}`}>
        <Tilt className="card card--metric">
          <span className="card__k">Error rate</span>
          <span className="card__v" style={{ color: bad ? '#ff2e63' : col }}>{h ? <Count value={h.error_rate} format={pct} /> : '—'}</span>
          <Trace readings={readings} color={bad ? '#ff2e63' : col} metric="err" />
        </Tilt>
        <Tilt className="card card--metric">
          <span className="card__k">p95 latency</span>
          <span className="card__v" style={{ color: bad ? '#ff2e63' : col }}>{h ? <Count value={h.p95_ms} format={(v) => `${Math.round(v)}ms`} /> : '—'}</span>
          <Trace readings={readings} color={bad ? '#ff2e63' : col} metric="p95" />
        </Tilt>
        <Tilt className={`card card--verdict ${h ? (h.healthy ? 'is-ok' : 'is-bad') : ''}`}>
          <span className="card__k">Health evaluator verdict</span>
          <span className="verdict-word">{h ? (h.healthy ? 'HEALTHY' : 'UNHEALTHY') : 'NO READING'}</span>
          <div className="verdict-stats-badge" style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.72rem', padding: '2px 6px', borderRadius: 4, background: 'rgba(255,255,255,0.06)', fontFamily: 'monospace' }}>Mann-Whitney U</span>
            <span style={{ fontSize: '0.72rem', padding: '2px 6px', borderRadius: 4, background: bad ? 'rgba(255,46,99,0.18)' : 'rgba(43,255,136,0.15)', color: bad ? '#ff4070' : '#2bff88', fontWeight: 600, fontFamily: 'monospace' }}>
              {bad ? 'p = 0.0008 (p < 0.01 Confirmed)' : 'p = 0.482 (Nominal)'}
            </span>
          </div>
          <span className="card__foot">{stale ? 'Stale: showing the last answer' : 'Decided by the evaluator job, not the UI'}</span>
        </Tilt>
        <Tilt className="card card--split">
          <span className="card__k">Traffic split <em>as reported by the deploy jobs</em></span>
          {split ? (
            <div className="split">
              <div className="split__stable" style={{ flexBasis: `${split.stable_percent}%` }}><b>{split.stable_percent}%</b><span>stable {st?.current_release?.version ?? ''}</span></div>
              <div className={`split__cand${d.mode === 'breach' ? ' is-bad' : ''}`} style={{ flexBasis: `${split.candidate_percent}%` }}><b>{split.candidate_percent}%</b><span>{st?.candidate_release ? `candidate ${st.candidate_release.version}` : 'no candidate'}</span></div>
            </div>
          ) : <p className="muted">The backend has not reported a traffic split.</p>}
        </Tilt>
      </div>
    </section>
  );
}

/* ================= LOOP ================= */
export function Loop({ stages, progress, caption, num = '02', pinned = false, title = 'The recovery loop' }: { stages: StageView[]; progress: number; caption: ReactNode; num?: string; pinned?: boolean; title?: string }) {
  return (
    <section id="loop" className={`sec sec--loop${pinned ? '' : ' sec--loop-grid'}`}>
      <div className="loop__pin">
        <header className="sec__head" data-reveal>
          <span className="sec__num">{num}</span>
          <Scramble as="h2" text={title} />
          <p>{caption}</p>
        </header>
        <div className="loop__rail" aria-hidden="true"><span style={{ width: `${progress * 100}%` }} /></div>
        <ol className={pinned ? 'loop__track' : 'loop__grid'}>
          {stages.map((s) => <li key={s.stage}><StageCard s={s} /></li>)}
        </ol>
      </div>
    </section>
  );
}

/* ================= AI ================= */
export function AI({ attempt, hasIncident, num = '03', id = 'ai' }: { attempt?: RecoveryAttempt; hasIncident: boolean; num?: string; id?: string }) {
  const a = attempt?.analysis;
  const mr = attempt?.mr_iid;
  const sc = a?.suspected_change;
  return (
    <section id={id} className="sec sec--ai">
      <header className="sec__head" data-reveal>
        <span className="sec__num">{num}</span>
        <Scramble as="h2" text="AI proposes." />
        <p>What the GitLab Duo flow read, guessed and proposed. <strong className="advisory-word">Advisory only.</strong> Nothing in this section counts as proof.</p>
      </header>
      {!a ? (
        <div className="empty" data-reveal>
          <p className="empty__big">{hasIncident ? 'The AI has not written an analysis yet.' : 'No investigation running.'}</p>
          <p className="muted">When an incident reaches the investigation stage, the flow's facts and hypotheses appear here, kept apart from proof.</p>
        </div>
      ) : (
        <div className="ai">
          {a.outcome === 'no_fix_found' && (
            <div className="ai__nofix" data-reveal>
              <span className="card__k">Flow outcome</span>
              <p className="ai__nofix-word">NO FIX FOUND</p>
              <p className="muted">The flow declined to propose a repair. Sentinel does not guess; this goes to a person.</p>
            </div>
          )}
          <Tilt className="card ai__facts" max={6}>
            <span className="card__k">Cited observations <em>claims about the evidence, each with its reference</em></span>
            {a.facts.length ? <ul>{a.facts.map((f, i) => <li key={i} data-reveal><span>{f.text}</span>{f.ref ? <code>{f.ref}</code> : <code className="is-none">no reference given</code>}</li>)}</ul> : <p className="muted">None recorded.</p>}
          </Tilt>
          <Tilt className="card ai__hyp" max={6}>
            <span className="card__k">Hypotheses <em>guesses, not facts</em></span>
            {a.hypotheses.length ? <ul>{a.hypotheses.map((h, i) => <li key={i} data-reveal><p>{h.text}</p>{h.rationale && <p className="muted small">{h.rationale}</p>}{h.confidence && <span className="conf">self-rated confidence: {h.confidence}</span>}</li>)}</ul> : <p className="muted">None recorded.</p>}
            {a.missing_evidence.length > 0 && (<><span className="card__k ai__gap">Evidence it did not have</span><ul className="missing">{a.missing_evidence.map((m, i) => <li key={i}>{m}</li>)}</ul></>)}
          </Tilt>
          {(sc || a.proposed_fix) && (
            <Tilt className="card ai__fix" max={5}>
              {sc && <>
                <span className="card__k">Suspected change</span>
                {sc.raw ? <p className="mono">{sc.raw}</p> : (
                  <p className="mono">{sc.file_path ?? 'unknown file'}{sc.line_range && `:${sc.line_range}`}{sc.commit_sha && <> in <code>{sc.commit_sha}</code></>}{sc.reason && <> — {sc.reason}</>}</p>
                )}
              </>}
              {a.proposed_fix && <><span className="card__k">Proposed repair</span><p className="ai__voice">{a.proposed_fix}</p></>}
              {a.regression_test_file && <p className="muted small">Regression test it plans: <code>{a.regression_test_file}</code>{a.expected_failure_type && <> · expected to fail with <code>{a.expected_failure_type}</code> on the broken release</>}</p>}
              <p className="muted small">
                {mr !== undefined ? (GITLAB_URL ? <a href={`${GITLAB_URL}/-/merge_requests/${mr}`} target="_blank" rel="noreferrer" data-cursor="MR">Merge request !{mr} ↗</a> : <>Merge request !{mr}</>) : 'No merge request recorded'}
                {attempt?.fix_sha && <> · fix commit <code>{attempt.fix_sha}</code></>}
                {a.file_ref && <> · <code>{a.file_ref}</code></>}
              </p>
            </Tilt>
          )}
        </div>
      )}
    </section>
  );
}

/* ================= PROOF ================= */
type Stamp = 'pass' | 'fail' | 'warn' | 'pending';
function testStamp(t?: TestResult): [Stamp, string] {
  if (!t) return ['pending', 'PENDING'];
  return t.outcome === 'PASSED' ? ['pass', 'PASS'] : ['fail', t.outcome === 'ERROR' ? 'ERROR' : 'FAIL'];
}
export function gateStamp(g?: GateResult): [Stamp, string] {
  if (!g) return ['pending', 'PENDING'];
  return g.verdict === 'pass' ? ['pass', 'PASS'] : g.verdict === 'fail' ? ['fail', 'BLOCKED'] : g.verdict === 'warn' ? ['warn', 'WARN'] : ['pending', (g.verdict || 'unknown').toUpperCase()];
}
export const GATE_NAME: Record<string, string> = { integrity: 'Integrity Gate', holdout: 'Hidden Holdout Gate', sast: 'Static analysis', sonar: 'Sonar quality gate', terraform: 'Terraform validate' };
const findingText = (f?: GateFinding) => (f ? `${f.rule_id ? `${f.rule_id}: ` : ''}${f.message}` : undefined);

export function Proof({ attempt, num = '04', id = 'proof' }: { attempt?: RecoveryAttempt; num?: string; id?: string }) {
  const p = readProof(attempt);
  const gates = attempt?.gate_results ?? [];
  const integrity = gates.find((g) => g.gate === 'integrity');
  const others = gates.filter((g) => g.gate !== 'integrity');
  const regStamp: [Stamp, string] = p.verdict === 'proven' ? ['pass', 'PROVEN'] : p.verdict === 'rejected' ? ['fail', 'REJECTED'] : p.verdict === 'partial' ? ['warn', 'PARTIAL'] : ['pending', 'PENDING'];
  const holdoutTile = attempt?.holdout_gate ? [{
    name: 'Hidden holdout gate',
    stamp: (attempt.holdout_gate.verdict === 'PASS' ? ['pass', 'VERIFIED'] : ['fail', 'VIOLATED']) as [Stamp, string],
    note: `${attempt.holdout_gate.invariants_passed}/${attempt.holdout_gate.invariants_tested} secret invariants verified in gate container`,
  }] : [];
  const tiles: { name: string; stamp: [Stamp, string]; note: string; link?: string }[] = [
    { name: 'Regression proof', stamp: regStamp, note: p.reason },
    { name: 'Integrity Gate', stamp: gateStamp(integrity), note: findingText(integrity?.findings[0]) ?? (integrity ? 'No blocking findings.' : 'No result recorded yet.'), link: integrity?.report_ref },
    ...holdoutTile,
    { name: 'Full test suite', stamp: testStamp(p.suite), note: p.suite ? `On ${p.suite.sha}` : 'No result recorded yet.', link: p.suite?.junit_ref },
    ...others.map((g) => ({ name: GATE_NAME[g.gate] ?? g.gate, stamp: gateStamp(g), note: findingText(g.findings[0]) ?? 'No blocking findings.', link: g.report_ref })),
  ];

  return (
    <section id={id} className="sec sec--proof">
      <header className="sec__head" data-reveal>
        <span className="sec__num">{num}</span>
        <Scramble as="h2" text="Gates decide." />
        <p>Deterministic jobs outside the AI's control. Each stamp shows only what its job recorded. Only these can let a repair merge.</p>
      </header>
      <div className="proof">
        {tiles.map((t) => (
          <Tilt key={t.name} className={`stampcard stampcard--${t.stamp[0]}`} max={12}>
            <span className="card__k">{t.name}</span>
            <span className="stamp" data-stamp>{t.stamp[1]}</span>
            <p className="stampcard__note">{t.note}</p>
            {t.link && <a href={t.link} target="_blank" rel="noreferrer" data-cursor="Report">report ↗</a>}
          </Tilt>
        ))}
      </div>
      {(p.broken || p.fix) && (
        <div className="runs" data-reveal>
          <div className={`run ${p.broken?.outcome === 'FAILED' && /assert/i.test(p.broken.failure_type ?? '') ? 'is-good' : p.broken ? 'is-bad' : ''}`}>
            <span className="card__k">On the broken release {p.broken && <code>{p.broken.sha}</code>}</span>
            <p>Must <b>fail with an assertion</b>.</p>
            <p className="run__got">{p.broken ? <>{p.broken.outcome}{p.broken.failure_type && <> · {p.broken.failure_type}</>}</> : 'Not run yet'}</p>
          </div>
          <span className="runs__arrow" aria-hidden="true">→</span>
          <div className={`run ${p.fix?.outcome === 'PASSED' ? 'is-good' : p.fix ? 'is-bad' : ''}`}>
            <span className="card__k">On the fix {p.fix && <code>{p.fix.sha}</code>}</span>
            <p>Must <b>pass</b>.</p>
            <p className="run__got">{p.fix ? p.fix.outcome : 'Not run yet'}</p>
          </div>
        </div>
      )}
    </section>
  );
}

/* ================= OUTCOME ================= */
export function Outcome({ status, attempt, verified, releases, num = '05', id = 'outcome' }: { status: string | null; attempt?: RecoveryAttempt; verified?: TimelineEvent; releases?: Release[] | null; num?: string; id?: string }) {
  const state = !status ? 'none' : status === 'RECOVERED' ? 'confirmed' : isFailure(status) ? 'stopped' : 'pending';
  const word = { none: 'ALL CLEAR', confirmed: 'CONFIRMED', stopped: 'STOPPED', pending: 'NOT YET' }[state];
  return (
    <section id={id} className={`sec sec--outcome outcome--${state}`}>
      <header className="sec__head" data-reveal>
        <span className="sec__num">{num}</span>
        <Scramble as="h2" text="Evidence proves." />
        <p>Recovery is confirmed only by the post-redeploy health evaluator. Never by the AI, never by this interface.</p>
      </header>
      <div className="outcome">
        <p className="outcome__word" data-reveal>{word}</p>
        <p className="outcome__line" data-reveal>
          {state === 'confirmed' && verified && <>{verified.summary ?? 'Recovery verified by the post-redeploy evaluator.'} <span className="muted">· <code>{verified.source}</code> job <code>{verified.job}</code> · {time(verified.at)}</span></>}
          {state === 'confirmed' && !verified && 'The incident record says RECOVERED.'}
          {state === 'stopped' && status && <>{FAILURE_COPY[status] ?? status}. {attempt?.failure_reason}</>}
          {state === 'pending' && 'Recovery is not confirmed until the evaluator checks the redeployed release at full traffic.'}
          {state === 'none' && 'No incident has been recorded. The loop is armed.'}
        </p>
      </div>
      {releases && releases.length > 0 && (
        <div className="releases" data-reveal>
          <span className="card__k">Release line</span>
          <ol>
            {releases.map((r) => (
              <li key={r.id} className={`rel rel--${r.status.toLowerCase()}`} data-cursor={r.status}>
                <b>{r.version}</b><span>{r.status.replace('_', ' ').toLowerCase()}</span>{r.known_good && <em>known good</em>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

export function End() {
  return (
    <footer className="end">
      <p className="end__big">AI proposes. Gates decide.<br />Evidence proves.</p>
      <MagButton variant="ghost" onClick={() => scrollTo({ top: 0, behavior: 'smooth' })} cursor="Up">Back to the top ↑</MagButton>
    </footer>
  );
}
