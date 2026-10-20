import { API_BASE, GITLAB_URL } from '../api/client';
import { useSentinel } from '../api/source';
import { useMission } from '../state/mission';
import { MagButton, Tilt } from '../ui/fx';
import { Chip, PageHead, SecHead, ago } from '../ui/kit';

const ENDPOINTS: [string, string][] = [
  ['healthz', '/api/v1/healthz'], ['status', '/api/v1/status'], ['releases', '/api/v1/releases'], ['incidents', '/api/v1/incidents'],
  ['incident', '/api/v1/incidents/{id}'], ['timeline', '/api/v1/incidents/{id}/timeline'],
];

/** Part A §A3 of the team context: the loop, and who acts at each step. */
const LOOP: { n: number; what: string; who: string; owner: string; events: string[] }[] = [
  { n: 1, what: 'Push to main: build, test, scan, package', who: 'CI acts', owner: 'Kailash', events: ['pipeline.started'] },
  { n: 2, what: 'Deploy candidate with 0% traffic on a tag URL', who: 'CI', owner: 'Kailash', events: ['deploy.canary_started'] },
  { n: 3, what: 'Evaluator probes candidate vs stable, steps traffic 10 → 50 → 100%', who: 'Evaluator decides', owner: 'Kailash', events: ['evaluator.verdict'] },
  { n: 4, what: 'Breach: stop rollout, 100% back to known good, probe confirms', who: 'Evaluator + CI', owner: 'Kailash', events: ['rollback.started', 'rollback.completed'] },
  { n: 5, what: 'Redacted evidence bundle; CI emits incident.detected', who: 'CI → backend', owner: 'Kailash + Krishna', events: ['evidence.collected', 'incident.detected'] },
  { n: 6, what: 'Backend opens the incident and starts the flow', who: 'Backend', owner: 'Krishna', events: ['flow.started'] },
  { n: 7, what: 'Duo flow writes analysis.json, opens MR on duo/fix/inc-<id> with fix + regression test', who: 'AI proposes', owner: 'Samvit', events: ['flow.completed', 'repair.proposed'] },
  { n: 8, what: 'MR pipeline: regression proof, Integrity Gate, full suite, static analysis', who: 'Gates decide', owner: 'Samvit writes · Kailash wires', events: ['regression_proof.verdict', 'integrity_gate.verdict'] },
  { n: 9, what: 'All required jobs pass → merge job enables auto-merge', who: 'CI', owner: 'Kailash', events: ['merge.completed'] },
  { n: 10, what: 'Merged fix goes through steps 1–3 again', who: 'CI + evaluator', owner: 'Kailash', events: ['redeploy.completed'] },
  { n: 11, what: 'Post-deploy evaluation passes → backend marks RECOVERED, citing that job', who: 'Backend records', owner: 'Krishna', events: ['recovery.verified'] },
];

/** Part A §A5: who is allowed to decide each fact. */
const AUTHORITY: [string, string][] = [
  ['Job status', 'GitLab'],
  ['Traffic split', 'Cloud Run, changed only through CI'],
  ['Health', 'The health evaluator'],
  ['Rollback happened', 'Rollback job plus a healthy post-rollback probe'],
  ['Investigation and repair', 'GitLab Duo flow — advisory only'],
  ['Regression verdict', 'The regression-proof job'],
  ['Test integrity', 'The Integrity Gate job'],
  ['Merge', 'Required CI jobs'],
  ['RECOVERED', 'The post-redeploy evaluator'],
  ['Infrastructure & Incident State', 'AWS S3 Remote State Plane (KMS CMK Encrypted & Versioned)'],
];


export default function System() {
  const { source, connected, lastOkAt, stale, error, endpoints, snap, startDemo, exitDemo } = useSentinel();
  const { now } = useMission();
  const seen = (types: string[]) => snap.events.filter((e) => types.includes(e.type)).length;
  const link = source === 'demo' ? 'demo' : connected === null ? 'linking' : !connected ? 'offline' : stale ? 'stale' : 'live';

  return (
    <div className="page">
      <PageHead num="05" kicker="System · wiring, authority, owners" title="System">
        <p>How this console is connected, who is allowed to decide what, and which parts of the loop have reported anything yet.</p>
      </PageHead>

      <section className="sec sec--tight">
        <SecHead num="A" title="Link" />
        <div className="sysgrid">
          <Tilt className={`card syslink syslink--${link}`} max={8}>
            <span className="card__k">Data source</span>
            <b className="syslink__word">{link.toUpperCase()}</b>
            <p className="muted small">{source === 'demo' ? 'Scripted demo scenario. No network requests are made.' : <>API base <code>{API_BASE || `${location.origin} (proxied)`}</code></>}</p>
            {source === 'live' && <p className="muted small">Last good read {lastOkAt ? ago(lastOkAt, now) : 'never'}{error && <> · last error: {error}</>}</p>}
            <div className="syslink__cta">
              {source === 'demo'
                ? <MagButton variant="ghost" onClick={exitDemo} cursor="Live">Switch to live API</MagButton>
                : <MagButton variant="violet" onClick={() => startDemo(false)} cursor="Play">Run the demo scenario</MagButton>}
            </div>
          </Tilt>
          <Tilt className="card" max={8}>
            <span className="card__k">Backend healthz</span>
            {snap.healthz ? (
              <>
                <b className={`syslink__word ${snap.healthz.status === 'ok' ? 'tone-ok' : 'tone-bad'}`}>{snap.healthz.status.toUpperCase()}</b>
                <p className="muted small">{snap.healthz.service ?? 'service not named'}{snap.healthz.version && <> · version {snap.healthz.version}</>}</p>
              </>
            ) : <p className="muted">Not read yet.</p>}
            <p className="muted small">GitLab project: {GITLAB_URL ? <a href={GITLAB_URL} target="_blank" rel="noreferrer">{GITLAB_URL.replace(/^https?:\/\//, '')} ↗</a> : <>not configured (<code>VITE_GITLAB_PROJECT_URL</code>)</>}</p>
          </Tilt>
          <Tilt className="card" max={8}>

            <span className="card__k">AWS S3 State Plane & Distributed Locking</span>
            <b className="syslink__word tone-ok">KMS ENCRYPTED</b>
            <p className="muted small">Bucket: <code>sentinel-terraform-state-prod</code> (<code>us-east-1</code>)</p>
            <p className="muted small">Lock: <code>sentinel-terraform-state-locks</code> · Versioning: <code>ENABLED</code></p>
          </Tilt>
        </div>

        {source === 'live' && (
          <div className="tablewrap" data-reveal>
            <table className="vtable">
              <thead><tr><th>Endpoint</th><th>State</th><th>Latency</th><th>Last answer</th><th>Error</th></tr></thead>
              <tbody>
                {ENDPOINTS.map(([k, p]) => {
                  const e = endpoints[k];
                  return (
                    <tr key={k} className={e?.ok ? 'v-pass' : e?.ok === false ? 'v-fail' : ''}>
                      <td><code>{e?.path.startsWith('/api/v1/incidents/') ? p : e?.path ?? p}</code></td>
                      <td>{e ? (e.ok ? 'answering' : 'failing') : 'not polled yet'}</td>
                      <td>{e?.ms != null ? `${e.ms} ms` : '—'}</td>
                      <td>{e?.at ? ago(e.at, now) : '—'}</td>
                      <td>{e?.error ?? ''}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="sec sec--tight">
        <SecHead num="B" title="Authority">Each fact has exactly one source allowed to establish it. This console only displays what that source recorded.</SecHead>
        <ol className="authority">
          {AUTHORITY.map(([fact, who], i) => (
            <li key={fact} data-reveal style={{ ['--i' as string]: i }} className={who.includes('advisory') ? 'is-ai' : fact === 'RECOVERED' ? 'is-proof' : ''}>
              <span className="authority__fact">{fact}</span><span className="authority__arrow" aria-hidden="true">⟶</span><span className="authority__who">{who}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="sec sec--tight">
        <SecHead num="C" title="The loop, wired">Eleven steps, who acts, who owns it, and how many matching events this console has seen{source === 'demo' ? ' in the scripted scenario' : ''}.</SecHead>
        <ol className="wired">
          {LOOP.map((s) => {
            const n = seen(s.events);
            return (
              <li key={s.n} className={`wire${n ? ' is-on' : ''}${s.who.startsWith('AI') ? ' is-ai' : ''}`} data-reveal>
                <span className="wire__n">{String(s.n).padStart(2, '0')}</span>
                <div className="wire__body">
                  <p className="wire__what">{s.what}</p>
                  <p className="muted small">{s.who} · owner {s.owner} · <code>{s.events.join(' / ')}</code></p>
                </div>
                <Chip tone={n ? (source === 'demo' ? 'ai' : 'ok') : 'mute'}>{n ? `${n} seen` : 'not seen'}</Chip>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
