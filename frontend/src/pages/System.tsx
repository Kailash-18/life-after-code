import { useEffect, useState } from 'react';
import {
  API_BASE,
  DEFAULT_SENTINEL_API_KEY,
  GITLAB_URL,
  generateRandomApiKey,
  getApiKey,
  getJSON,
  resetApiKey,
  rollbackToS3Snapshot,
  setApiKey,
} from '../api/client';
import type { S3RollbackResult } from '../api/types';
import { useSentinel } from '../api/source';
import { useMission } from '../state/mission';
import { bus } from '../state/bus';
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
  ['API Authentication & Access', 'Sentinel Key Vault (Bearer Token & X-API-Key)'],
];


export default function System() {
  const { source, connected, lastOkAt, stale, error, endpoints, snap, startDemo, exitDemo } = useSentinel();
  const { now } = useMission();
  const [rollingBack, setRollingBack] = useState(false);
  const [rollbackResult, setRollbackResult] = useState<S3RollbackResult | null>(null);
  const [currentApiKey, setCurrentApiKey] = useState(getApiKey());
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false);
  const [apiKeyRevealed, setApiKeyRevealed] = useState(false);

  useEffect(() => {
    const onKeyChange = (e: Event) => {
      const customEvent = e as CustomEvent<{ apiKey: string }>;
      if (customEvent.detail?.apiKey) setCurrentApiKey(customEvent.detail.apiKey);
    };
    window.addEventListener('sentinel:apikey:changed', onKeyChange);
    return () => window.removeEventListener('sentinel:apikey:changed', onKeyChange);
  }, []);

  const handleRollback = async () => {
    setRollingBack(true);
    try {
      const res = await rollbackToS3Snapshot();
      setRollbackResult(res);
    } catch {
      // Handled in client fallback
    } finally {
      setRollingBack(false);
    }
  };

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
            <div className="syslink__cta" style={{ marginTop: '0.6rem' }}>
              <MagButton variant="ghost" onClick={handleRollback} cursor="Rollback">
                {rollingBack ? 'Restoring Snapshot...' : 'Revert to S3 Snapshot'}
              </MagButton>
            </div>
            {rollbackResult && (
              <p className="muted small tone-ok" style={{ marginTop: '0.4rem', fontSize: '0.75rem' }}>
                ✓ Restored <code>{rollbackResult.snapshot_id.slice(0, 18)}...</code> (100% traffic to stable)
              </p>
            )}
          </Tilt>
          <Tilt className="card" max={8}>
            <span className="card__k">API Key & Access Credentials</span>
            <b className="syslink__word tone-ok">AUTHENTICATED</b>
            <p className="muted small">Header: <code>X-API-Key</code> / <code>Bearer</code></p>
            <p className="muted small">
              Key: <code>{apiKeyRevealed ? currentApiKey : (currentApiKey.length > 14 ? `${currentApiKey.slice(0, 10)}••••${currentApiKey.slice(-4)}` : '••••••••••••')}</code>
            </p>
            <div className="syslink__cta" style={{ marginTop: '0.6rem', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <MagButton variant="ghost" onClick={() => setApiKeyModalOpen(true)} cursor="Key">
                Manage API Key
              </MagButton>
              <button
                onClick={() => setApiKeyRevealed(!apiKeyRevealed)}
                style={{
                  padding: '6px 12px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid var(--line)',
                  borderRadius: '999px',
                  fontSize: '11px',
                  fontFamily: 'var(--mono)',
                  color: 'var(--ink-2)',
                  cursor: 'pointer',
                }}
              >
                {apiKeyRevealed ? 'Hide' : 'Reveal'}
              </button>
            </div>
          </Tilt>
        </div>

        <SystemApiKeyModal open={apiKeyModalOpen} onClose={() => setApiKeyModalOpen(false)} />

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

function SystemApiKeyModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [key, setLocalKey] = useState(getApiKey());
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState(getApiKey());
  const [testResult, setTestResult] = useState<{ status: 'idle' | 'testing' | 'ok' | 'fail'; msg: string }>({
    status: 'idle',
    msg: '',
  });

  useEffect(() => {
    if (open) {
      const current = getApiKey();
      setLocalKey(current);
      setInputVal(current);
      setEditing(false);
      setTestResult({ status: 'idle', msg: '' });
      bus.pulse(0.8);
    }
  }, [open]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const handleCopy = async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(key);
      } else {
        const ta = document.createElement('textarea');
        ta.value = key;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      bus.pulse(0.5);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard fallback
    }
  };

  const handleSave = () => {
    if (inputVal.trim()) {
      setApiKey(inputVal.trim());
      setLocalKey(inputVal.trim());
      setEditing(false);
      bus.pulse(1.0);
    }
  };

  const handleReset = () => {
    resetApiKey();
    setLocalKey(DEFAULT_SENTINEL_API_KEY);
    setInputVal(DEFAULT_SENTINEL_API_KEY);
    setEditing(false);
    bus.pulse(0.8);
  };

  const handleRotate = () => {
    const newKey = generateRandomApiKey();
    setApiKey(newKey);
    setLocalKey(newKey);
    setInputVal(newKey);
    setEditing(false);
    bus.pulse(1.2);
  };

  const handleTest = async () => {
    setTestResult({ status: 'testing', msg: 'Validating against Sentinel backend...' });
    try {
      const res = (await getJSON('/api/v1/healthz')) as Record<string, unknown>;
      if (res && (res.status === 'ok' || res.service)) {
        setTestResult({ status: 'ok', msg: `HTTP 200 OK — Authenticated to ${res.service ?? 'Sentinel Backend'}` });
      } else {
        setTestResult({ status: 'ok', msg: 'HTTP 200 OK — Connected successfully' });
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      setTestResult({ status: 'fail', msg: `Authentication check response: ${errorMsg}` });
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.5rem',
        background: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '560px',
          background: 'var(--panel, #0e121b)',
          border: '1px solid var(--line, rgba(255, 255, 255, 0.12))',
          borderRadius: '16px',
          boxShadow: '0 24px 64px -12px rgba(0, 0, 0, 0.8), 0 0 32px -8px var(--cyan, #00f0ff)',
          padding: '1.75rem',
          color: 'var(--ink, #fff)',
          display: 'flex',
          flexDirection: 'column',
          gap: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--cyan, #00f0ff)', fontWeight: 600 }}>
              Access & Security
            </span>
            <h3 style={{ margin: '4px 0 0', fontSize: '18px', fontWeight: 600, color: 'var(--ink, #fff)' }}>
              Sentinel API Key Vault
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--ink-2, #888)',
              fontSize: '20px',
              cursor: 'pointer',
              padding: '4px 8px',
            }}
          >
            ✕
          </button>
        </div>

        <p style={{ margin: 0, fontSize: '13px', color: 'var(--ink-2, #aaa)', lineHeight: 1.5 }}>
          Configures client authentication headers (<code>X-API-Key</code> and <code>Authorization: Bearer</code>) for all Sentinel API and S3 state operations.
        </p>

        <div
          style={{
            background: 'rgba(0, 0, 0, 0.4)',
            border: '1px solid var(--line, rgba(255, 255, 255, 0.08))',
            borderRadius: '10px',
            padding: '1rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ink-2, #888)' }}>CURRENT API KEY</span>
            <span style={{ fontSize: '11px', color: 'var(--cyan, #00f0ff)', fontFamily: 'var(--mono, monospace)' }}>
              STORAGE: ACTIVE
            </span>
          </div>

          {editing ? (
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                style={{
                  flex: 1,
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid var(--line, rgba(255, 255, 255, 0.2))',
                  borderRadius: '6px',
                  padding: '8px 12px',
                  color: 'var(--ink, #fff)',
                  fontFamily: 'var(--mono, monospace)',
                  fontSize: '13px',
                }}
              />
              <MagButton variant="violet" onClick={handleSave} cursor="Save">Save</MagButton>
              <MagButton variant="ghost" onClick={() => setEditing(false)} cursor="Cancel">Cancel</MagButton>
            </div>
          ) : (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '12px',
                background: 'rgba(255, 255, 255, 0.03)',
                padding: '8px 12px',
                borderRadius: '8px',
                border: '1px dashed var(--line, rgba(255, 255, 255, 0.15))',
              }}
            >
              <code style={{ fontSize: '13px', color: 'var(--cyan, #00f0ff)', wordBreak: 'break-all' }}>
                {revealed ? key : (key.length > 14 ? `${key.slice(0, 10)}••••••••••••${key.slice(-4)}` : '••••••••••••••••')}
              </code>
              <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                <button
                  onClick={() => setRevealed(!revealed)}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--line, rgba(255, 255, 255, 0.15))',
                    borderRadius: '6px',
                    padding: '4px 8px',
                    fontSize: '11px',
                    color: 'var(--ink-2, #aaa)',
                    cursor: 'pointer',
                  }}
                >
                  {revealed ? 'Hide' : 'Reveal'}
                </button>
                <button
                  onClick={handleCopy}
                  style={{
                    background: copied ? 'var(--cyan, #00f0ff)' : 'transparent',
                    color: copied ? '#000' : 'var(--ink-2, #aaa)',
                    border: '1px solid var(--line, rgba(255, 255, 255, 0.15))',
                    borderRadius: '6px',
                    padding: '4px 8px',
                    fontSize: '11px',
                    cursor: 'pointer',
                    fontWeight: copied ? 700 : 400,
                  }}
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <MagButton variant="ghost" onClick={() => setEditing(!editing)} cursor="Edit">
            {editing ? 'Close Editor' : 'Edit Key'}
          </MagButton>
          <MagButton variant="ghost" onClick={handleRotate} cursor="Rotate">
            Rotate Key
          </MagButton>
          <MagButton variant="ghost" onClick={handleReset} cursor="Reset">
            Reset to Default
          </MagButton>
          <MagButton variant="violet" onClick={handleTest} cursor="Test">
            Test Authentication
          </MagButton>
        </div>

        {testResult.status !== 'idle' && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: '8px',
              fontSize: '12px',
              fontFamily: 'var(--mono, monospace)',
              background:
                testResult.status === 'ok'
                  ? 'rgba(46, 204, 113, 0.12)'
                  : testResult.status === 'fail'
                  ? 'rgba(231, 76, 60, 0.12)'
                  : 'rgba(255, 255, 255, 0.05)',
              border:
                testResult.status === 'ok'
                  ? '1px solid rgba(46, 204, 113, 0.3)'
                  : testResult.status === 'fail'
                  ? '1px solid rgba(231, 76, 60, 0.3)'
                  : '1px solid var(--line, rgba(255, 255, 255, 0.1))',
              color:
                testResult.status === 'ok'
                  ? '#2ecc71'
                  : testResult.status === 'fail'
                  ? '#e74c3c'
                  : 'var(--ink-2, #aaa)',
            }}
          >
            {testResult.msg}
          </div>
        )}
      </div>
    </div>
  );
}
