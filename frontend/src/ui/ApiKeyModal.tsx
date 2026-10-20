import { useEffect, useState } from 'react';
import {
  API_BASE,
  DEFAULT_SENTINEL_API_KEY,
  generateRandomApiKey,
  getApiKey,
  getJSON,
  resetApiKey,
  setApiKey,
} from '../api/client';
import { bus } from '../state/bus';

interface ApiKeyModalProps {
  open: boolean;
  onClose: () => void;
}

export function ApiKeyModal({ open, onClose }: ApiKeyModalProps) {
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
    const onKeyChange = (e: Event) => {
      const customEvent = e as CustomEvent<{ apiKey: string }>;
      if (customEvent.detail?.apiKey) {
        setLocalKey(customEvent.detail.apiKey);
        setInputVal(customEvent.detail.apiKey);
      }
    };
    window.addEventListener('sentinel:apikey:changed', onKeyChange);
    return () => window.removeEventListener('sentinel:apikey:changed', onKeyChange);
  }, []);

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
      await navigator.clipboard.writeText(key);
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

  const handleGenerate = () => {
    const newKey = generateRandomApiKey();
    setInputVal(newKey);
    setApiKey(newKey);
    setLocalKey(newKey);
    setEditing(false);
    bus.pulse(1.2);
  };

  const handleTestKey = async () => {
    setTestResult({ status: 'testing', msg: 'Validating key credentials with Sentinel API...' });
    const t0 = performance.now();
    try {
      await getJSON('/api/v1/healthz');
      const ms = Math.round(performance.now() - t0);
      setTestResult({
        status: 'ok',
        msg: `200 OK — Authenticated successfully (${ms}ms) via Bearer / X-API-Key`,
      });
      bus.pulse(1.0);
    } catch (err: unknown) {
      setTestResult({
        status: 'fail',
        msg: `Validation Warning: ${err instanceof Error ? err.message : 'API offline or key rejected'}`,
      });
    }
  };

  const masked = key.length > 12 ? `${key.slice(0, 10)}••••••••••••••••${key.slice(-4)}` : '••••••••••••••••';

  return (
    <div
      className="palette"
      role="dialog"
      aria-modal="true"
      aria-label="Sentinel API Key Credentials"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="palette__box" style={{ maxWidth: '640px', padding: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '20px' }}>🔑</span>
            <div>
              <h2 style={{ font: '700 14px/1.2 var(--display)', letterSpacing: '0.12em', color: 'var(--cyan)' }}>
                SENTINEL API KEY CREDENTIALS
              </h2>
              <p className="muted small" style={{ margin: '4px 0 0' }}>
                Zero-Trust SRE Access Token & Automated CI Ingestion Authentication
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="kbtn"
            style={{ width: '32px', height: '32px', padding: 0, justifyContent: 'center' }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Current Key Card */}
        <div
          style={{
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid var(--line-2)',
            borderRadius: '12px',
            padding: '16px',
            marginBottom: '16px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span className="card__k" style={{ fontSize: '11px' }}>ACTIVE CREDENTIAL KEY</span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => setRevealed(!revealed)}
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--mono)',
                  color: 'var(--ink-2)',
                  textDecoration: 'underline',
                  cursor: 'pointer',
                }}
              >
                {revealed ? 'Hide Key' : 'Reveal Key'}
              </button>
              <button
                onClick={handleCopy}
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--mono)',
                  color: copied ? 'var(--green)' : 'var(--cyan)',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                {copied ? '✓ Copied!' : 'Copy Key'}
              </button>
            </div>
          </div>

          <div
            style={{
              fontFamily: 'var(--mono)',
              fontSize: '13px',
              padding: '10px 14px',
              background: 'rgba(0, 0, 0, 0.4)',
              border: '1px solid rgba(60, 240, 255, 0.2)',
              borderRadius: '8px',
              color: 'var(--ink)',
              wordBreak: 'break-all',
              userSelect: 'all',
            }}
          >
            {revealed ? key : masked}
          </div>

          {editing ? (
            <div style={{ marginTop: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <input
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                placeholder="Paste custom API key (e.g. sk-sentinel-...)"
                style={{
                  flex: 1,
                  minWidth: '220px',
                  padding: '8px 12px',
                  background: 'rgba(10, 14, 18, 0.8)',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  color: 'var(--ink)',
                  fontFamily: 'var(--mono)',
                  fontSize: '12px',
                }}
              />
              <button
                onClick={handleSave}
                style={{
                  padding: '8px 16px',
                  background: 'var(--cyan)',
                  color: '#000',
                  fontWeight: 700,
                  fontSize: '11px',
                  borderRadius: '6px',
                  letterSpacing: '0.08em',
                  cursor: 'pointer',
                }}
              >
                SAVE
              </button>
              <button
                onClick={() => setEditing(false)}
                style={{
                  padding: '8px 12px',
                  background: 'transparent',
                  color: 'var(--muted)',
                  fontSize: '11px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                }}
              >
                CANCEL
              </button>
            </div>
          ) : (
            <div style={{ marginTop: '12px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button
                onClick={() => setEditing(true)}
                style={{
                  padding: '6px 12px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontFamily: 'var(--mono)',
                  color: 'var(--ink-2)',
                  cursor: 'pointer',
                }}
              >
                ✎ Edit Key
              </button>
              <button
                onClick={handleGenerate}
                style={{
                  padding: '6px 12px',
                  background: 'rgba(167, 123, 255, 0.1)',
                  border: '1px solid rgba(167, 123, 255, 0.3)',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontFamily: 'var(--mono)',
                  color: 'var(--violet)',
                  cursor: 'pointer',
                }}
              >
                ⚡ Generate Rotated Key
              </button>
              <button
                onClick={handleReset}
                style={{
                  padding: '6px 12px',
                  background: 'transparent',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontFamily: 'var(--mono)',
                  color: 'var(--muted)',
                  cursor: 'pointer',
                }}
              >
                ↺ Reset Default
              </button>
            </div>
          )}
        </div>

        {/* Live Validation & Usage Details */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px', marginBottom: '16px' }}>
          <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
            <span className="card__k" style={{ fontSize: '10px' }}>HEADER SPECIFICATION</span>
            <pre style={{ margin: '6px 0 0', fontSize: '11px', fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
              X-API-Key: {key.slice(0, 14)}...{'\n'}
              Authorization: Bearer {key.slice(0, 8)}...
            </pre>
          </div>

          <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '12px', borderRadius: '8px', border: '1px solid var(--line)' }}>
            <span className="card__k" style={{ fontSize: '10px' }}>AUTHENTICATED PRIVILEGES</span>
            <ul style={{ margin: '6px 0 0', padding: 0, listStyle: 'none', fontSize: '11px', color: 'var(--ink-2)' }}>
              <li>✓ S3 Remote State Snapshots</li>
              <li>✓ Authoritative Rollback Trigger</li>
              <li>✓ Canary Traffic & SRE Telemetry</li>
            </ul>
          </div>
        </div>

        {/* Live Test */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '10px 14px', background: 'rgba(60, 240, 255, 0.05)', borderRadius: '8px', border: '1px solid rgba(60, 240, 255, 0.2)' }}>
          <div style={{ fontSize: '12px' }}>
            <b style={{ color: testResult.status === 'ok' ? 'var(--green)' : testResult.status === 'fail' ? 'var(--rose)' : 'var(--cyan)' }}>
              {testResult.status === 'testing' ? 'Testing...' : testResult.status === 'ok' ? 'Online & Authenticated' : testResult.status === 'fail' ? 'Connection Warning' : 'Ready'}
            </b>
            <p className="muted small" style={{ margin: '2px 0 0' }}>
              {testResult.msg || `Target: ${API_BASE || `${location.origin} (proxied)`}`}
            </p>
          </div>
          <button
            onClick={handleTestKey}
            disabled={testResult.status === 'testing'}
            style={{
              padding: '6px 14px',
              background: 'var(--cyan)',
              color: '#000',
              fontWeight: 700,
              fontSize: '11px',
              borderRadius: '6px',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {testResult.status === 'testing' ? 'Pinging...' : 'Test Connection'}
          </button>
        </div>
      </div>
    </div>
  );
}
