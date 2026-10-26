import { useEffect, useState } from 'react';
import {
  API_BASE,
  GITLAB_URL,
  getAdaptiveDriftStatus,
  getDisasterRecoveryStatus,
  getEBPFTelemetry,
  getOPACompliance,
  getS3StorageStatus,
  getSRECompositeHealth,
} from '../api/client';
import { useSentinel } from '../api/source';
import type {
  DataSource,
  AdaptiveDriftStatus,
  DisasterRecoveryStatus,
  EBPFTelemetryReport,
  OPAComplianceReport,
  S3StorageStatus,
  SRECompositeHealth,
} from '../api/types';
import { useMission } from '../state/mission';
import { MagButton, Tilt } from '../ui/fx';
import { Chip, PageHead, SecHead, ago } from '../ui/kit';

const ENDPOINTS: [string, string][] = [
  ['healthz', '/api/v1/healthz'],
  ['status', '/api/v1/status'],
  ['releases', '/api/v1/releases'],
  ['incidents', '/api/v1/incidents'],
  ['events', '/api/v1/events'],
  ['storage', '/api/v1/state/storage'],
  ['sre_health', '/api/v1/sre/health'],
  ['sre_opa', '/api/v1/sre/opa'],
  ['sre_ebpf', '/api/v1/sre/ebpf'],
  ['sre_dr', '/api/v1/sre/dr'],
  ['sre_drift', '/api/v1/sre/drift'],
  ['incident', '/api/v1/incidents/{id}'],
  ['timeline', '/api/v1/incidents/{id}/timeline'],
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
  ['Incident record', 'Sentinel backend, from HMAC-signed CI events only'],
];

/** Read-only view of the backend's state-storage report. Shows what it says, labelled for what it is. */
function StateStorage() {
  const { source } = useSentinel();
  const { now } = useMission();
  const [st, setSt] = useState<{ v: S3StorageStatus | null; err: string | null; at: number | null }>({ v: null, err: null, at: null });
  useEffect(() => {
    if (source !== 'live') return;
    const ctrl = new AbortController();
    const read = () => getS3StorageStatus(ctrl.signal)
      .then((v) => setSt({ v, err: null, at: Date.now() }))
      .catch((e: Error) => setSt((s) => ({ ...s, err: e.message })));
    read();
    const t = setInterval(read, 15_000);
    return () => { ctrl.abort(); clearInterval(t); };
  }, [source]);
  const v = st.v;
  return (
    <Tilt className="card" max={8}>
      <span className="card__k">Incident state storage</span>
      {source === 'demo' ? <p className="muted">Not read in the demo scenario.</p> : !v ? (
        <p className="muted">{st.err ? `Not readable: ${st.err}` : 'Not read yet.'}</p>
      ) : (
        <>
          <b className={`syslink__word ${v.s3_connected ? 'tone-ok' : 'tone-warn'}`}>{v.s3_connected ? 'S3 CONNECTED' : 'LOCAL ONLY'}</b>
          <p className="muted small">{v.s3_connected ? 'The backend reached its S3 bucket.' : 'The backend has no S3 connection; snapshots stay on its local disk.'} {v.total_snapshots_recorded ?? 0} snapshot{v.total_snapshots_recorded === 1 ? '' : 's'} recorded{v.last_sync_timestamp ? `, last ${ago(v.last_sync_timestamp, now)}` : ''}.</p>
          <p className="muted small">{v.bucket_name
            ? <>Configured bucket <code>{v.bucket_name}</code>{v.region && <> ({v.region})</>}{v.encryption?.algorithm && <>, encryption <code>{v.encryption.algorithm}</code></>} — as the backend reports it.</>
            : 'No S3 bucket is configured.'}</p>
        </>
      )}
      <p className="muted small">Read-only. Rollbacks and traffic changes happen only through CI jobs.</p>
    </Tilt>
  );
}

const SOURCE_LABEL: Record<DataSource['kind'], string> = {
  measured: 'Measured',
  derived: 'Derived from a measurement',
  reference: 'Reference input',
  simulated: 'Simulated',
};

/** States where a panel's numbers come from, so simulated values are never read as telemetry. */
function SourceTag({ ds }: { ds?: DataSource }) {
  if (!ds) return null;
  return (
    <p className="muted small" style={{ marginTop: 8 }}>
      <Chip tone={ds.kind === 'measured' ? 'ok' : 'warn'}>{SOURCE_LABEL[ds.kind] ?? ds.kind}</Chip> {ds.note}
    </p>
  );
}

function SREOperations() {
  const { source, demoFail } = useSentinel();
  const [sre, setSre] = useState<SRECompositeHealth | null>(null);
  const [opa, setOpa] = useState<OPAComplianceReport | null>(null);
  const [ebpf, setEbpf] = useState<EBPFTelemetryReport | null>(null);
  const [dr, setDr] = useState<DisasterRecoveryStatus | null>(null);
  const [drift, setDrift] = useState<AdaptiveDriftStatus | null>(null);

  useEffect(() => {
    if (source === 'demo') {
      if (!demoFail) {
        setSre({
          health_score: 98.5,
          status: 'PASS',
          error_budget: {
            burn_rate: 0.05,
            alert_tier: 'NORMAL',
            hours_to_exhaustion: 720.0,
            recommended_action: 'HEALTHY: Error budget consumption well within SLO envelope',
          },
          hypothesis_testing: {
            p_value: 0.4821,
            is_significant: false,
            interpretation: 'Latency delta within expected statistical variance / null hypothesis retained',
          },
          latency_iqr: { median: 24.5, q1: 21.0, q3: 28.2, iqr: 7.2, outlier_threshold: 39.0 },
          statistical_anomalies_detected: 0,
        });
        setOpa({
          timestamp: new Date().toISOString(),
          policy_package: 'sentinel.security.guardrails',
          allow: true,
          compliance_score: 100.0,
          total_guardrails: 8,
          violations_count: 0,
          violations: [],
          status: 'APPROVED',
        });
        setEbpf({
          timestamp: new Date().toISOString(),
          samples_collected: 10,
          mean_transport_health_score: 98.4,
          status: 'PASS',
          latency_decomposition_averages_ms: {
            dns_resolution: 1.45,
            tcp_handshake: 2.30,
            tls_handshake: 6.20,
            server_ttfb: 18.50,
          },
          kernel_socket_aggregates: {
            total_tcp_retransmits: 0,
            total_syn_queue_drops: 0,
            retransmission_rate: 0.0,
          },
        });
        setDr({
          timestamp: new Date().toISOString(),
          primary_region: 'us-central1',
          secondary_region: 'us-east1',
          active_region: 'us-central1',
          rto_seconds: 1.85,
          rpo_seconds: 0.0,
          status: 'OPTIMAL',
        });
        setDrift({
          timestamp: new Date().toISOString(),
          observed_value: 24.5,
          current_ewma: 25.1,
          cusum_high_statistic: 0.0,
          cusum_low_statistic: 0.0,
          decision_threshold_h: 16.8,
          drift_detected: false,
          status: 'NOMINAL',
          action: 'NOMINAL: Process mean centered within allowable variance envelope',
        });
      } else {
        setSre({
          health_score: 52.0,
          status: 'FAIL',
          error_budget: {
            burn_rate: 18.4,
            alert_tier: 'PAGE_SEVERITY_1',
            hours_to_exhaustion: 39.1,
            recommended_action: 'CRITICAL_CIRCUIT_BREAK: Abort rollout immediately; error budget draining rapidly',
          },
          hypothesis_testing: {
            p_value: 0.0008,
            is_significant: true,
            interpretation: 'Statistically significant latency regression confirmed (p < 0.05)',
          },
          latency_iqr: { median: 142.0, q1: 95.0, q3: 210.0, iqr: 115.0, outlier_threshold: 382.5 },
          statistical_anomalies_detected: 6,
        });
        setOpa({
          timestamp: new Date().toISOString(),
          policy_package: 'sentinel.security.guardrails',
          allow: false,
          compliance_score: 75.0,
          total_guardrails: 8,
          violations_count: 2,
          violations: [
            "Container 'target-app' is missing authoritative CPU resource limits",
            "Initial canary traffic split (25%) exceeds maximum blast radius tolerance of 10%",
          ],
          status: 'REJECTED_BY_POLICY_GATE',
        });
        setEbpf({
          timestamp: new Date().toISOString(),
          samples_collected: 10,
          mean_transport_health_score: 64.2,
          status: 'FAIL',
          latency_decomposition_averages_ms: {
            dns_resolution: 3.20,
            tcp_handshake: 48.50,
            tls_handshake: 85.00,
            server_ttfb: 184.20,
          },
          kernel_socket_aggregates: {
            total_tcp_retransmits: 14,
            total_syn_queue_drops: 4,
            retransmission_rate: 0.12,
          },
        });
        setDr({
          timestamp: new Date().toISOString(),
          primary_region: 'us-central1',
          secondary_region: 'us-east1',
          active_region: 'us-central1',
          rto_seconds: 4.20,
          rpo_seconds: 0.0,
          status: 'OPTIMAL',
        });
        setDrift({
          timestamp: new Date().toISOString(),
          observed_value: 142.0,
          current_ewma: 88.4,
          cusum_high_statistic: 24.5,
          cusum_low_statistic: 0.0,
          decision_threshold_h: 16.8,
          drift_detected: true,
          status: 'HIGH_DRIFT_DETECTED',
          action: 'HIGH DRIFT DETECTED: Latency distribution shifted significantly above historical baseline',
        });
      }
      return;
    }

    const ctrl = new AbortController();
    const fetchSre = () => {
      getSRECompositeHealth(ctrl.signal).then(setSre).catch(() => {});
      getOPACompliance(ctrl.signal).then(setOpa).catch(() => {});
      getEBPFTelemetry(ctrl.signal).then(setEbpf).catch(() => {});
      getDisasterRecoveryStatus(ctrl.signal).then(setDr).catch(() => {});
      getAdaptiveDriftStatus(ctrl.signal).then(setDrift).catch(() => {});
    };
    fetchSre();
    const timer = setInterval(fetchSre, 15_000);
    return () => { ctrl.abort(); clearInterval(timer); };
  }, [source, demoFail]);

  return (
    <section className="sec sec--tight">
      <SecHead num="B" title="SRE Platform Telemetry & Observability Center">
        Statistical hypothesis testing, multi-window error budget burn rate, OPA Zero-Trust Rego guardrails, L4/L7 eBPF socket decomposition, and multi-region disaster recovery SLAs.
      </SecHead>
      <div className="sre-grid">
        <Tilt className="card" max={8}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span className="card__k">Google SRE Error Budget & Rank-Sum</span>
            {sre && <Chip tone={sre.status === 'PASS' ? 'ok' : sre.status === 'WARN' ? 'warn' : 'bad'}>{sre.status}</Chip>}
          </div>
          <b className={`syslink__word ${sre?.status === 'PASS' ? 'tone-ok' : sre?.status === 'WARN' ? 'tone-warn' : 'tone-bad'}`}>
            {sre ? (sre.health_score === null ? 'NO DATA' : `${sre.health_score} / 100`) : 'POLLING…'}
          </b>
          {sre && (!sre.error_budget || !sre.hypothesis_testing) ? (
            <p className="muted small" style={{ marginTop: 12 }}>No evaluator measurement recorded yet, so there is nothing to score.</p>
          ) : sre && sre.error_budget && sre.hypothesis_testing ? (
            <div style={{ marginTop: 12 }}>
              <div className="sre-metric-row">
                <span className="muted">Burn Rate</span>
                <code>{sre.error_budget.burn_rate}x ({sre.error_budget.alert_tier})</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Budget Exhaustion</span>
                <span>{sre.error_budget.hours_to_exhaustion} hrs</span>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Mann-Whitney p-value</span>
                <code>p = {sre.hypothesis_testing.p_value} {sre.hypothesis_testing.is_significant ? '(REGRESSION)' : '(STABLE)'}</code>
              </div>
              {sre.latency_iqr && (
                <div className="sre-metric-row">
                  <span className="muted">Latency IQR (p50 / Outlier)</span>
                  <span>{sre.latency_iqr.median}ms / {sre.latency_iqr.outlier_threshold}ms</span>
                </div>
              )}
              <p className="muted small" style={{ marginTop: 8 }}>{sre.error_budget.recommended_action ?? sre.hypothesis_testing.interpretation}</p>
            </div>
          ) : <p className="muted small">Awaiting statistical evaluator response.</p>}
          <SourceTag ds={sre?.data_source} />
        </Tilt>

        <Tilt className="card" max={8}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span className="card__k">OPA Rego Policy-as-Code</span>
            {opa && <Chip tone={opa.allow ? 'ok' : 'bad'}>{opa.status}</Chip>}
          </div>
          <b className={`syslink__word ${opa?.allow ? 'tone-ok' : 'tone-bad'}`}>
            {opa ? `${opa.compliance_score}% COMPLIANT` : 'POLLING…'}
          </b>
          {opa ? (
            <div style={{ marginTop: 12 }}>
              <div className="sre-metric-row">
                <span className="muted">Package</span>
                <code>{opa.policy_package}</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Guardrails Enforced</span>
                <span>{opa.total_guardrails} rules armed</span>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Violations</span>
                <span className={opa.violations_count > 0 ? 'tone-bad' : 'tone-ok'}>{opa.violations_count} detected</span>
              </div>
              <p className="muted small" style={{ marginTop: 8 }}>
                {opa.allow
                  ? 'Every policy in the package passed for the evaluated manifest.'
                  : `Blocked by Policy Gate: ${opa.violations[0] ?? 'Rule violations present'}`}
              </p>
            </div>
          ) : <p className="muted small">Awaiting OPA Rego policy engine response.</p>}
          <SourceTag ds={opa?.data_source} />
        </Tilt>

        <Tilt className="card" max={8}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span className="card__k">L4/L7 eBPF Socket Tracing</span>
            {ebpf && <Chip tone={ebpf.status === 'PASS' ? 'ok' : 'bad'}>{ebpf.status}</Chip>}
          </div>
          <b className={`syslink__word ${ebpf?.status === 'PASS' ? 'tone-ok' : 'tone-bad'}`}>
            {ebpf ? `${ebpf.mean_transport_health_score} HEALTH` : 'POLLING…'}
          </b>
          {ebpf ? (
            <div style={{ marginTop: 12 }}>
              <div className="sre-metric-row">
                <span className="muted">DNS Resolution</span>
                <code>{ebpf.latency_decomposition_averages_ms.dns_resolution} ms</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">TCP 3-Way Handshake</span>
                <code>{ebpf.latency_decomposition_averages_ms.tcp_handshake} ms</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">TLS 1.3 Key Exchange</span>
                <code>{ebpf.latency_decomposition_averages_ms.tls_handshake} ms</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Server TTFB</span>
                <code>{ebpf.latency_decomposition_averages_ms.server_ttfb} ms</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Kernel TCP Retransmits</span>
                <span className={ebpf.kernel_socket_aggregates.total_tcp_retransmits > 0 ? 'tone-bad' : 'tone-ok'}>
                  {ebpf.kernel_socket_aggregates.total_tcp_retransmits} retransmits
                </span>
              </div>
            </div>
          ) : <p className="muted small">Awaiting eBPF socket lifecycle probe.</p>}
          <SourceTag ds={ebpf?.data_source} />
        </Tilt>

        <Tilt className="card" max={8}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span className="card__k">Multi-Region Disaster Recovery</span>
            {dr && <Chip tone={dr.status === 'OPTIMAL' ? 'ok' : 'warn'}>{dr.status}</Chip>}
          </div>
          <b className={`syslink__word ${dr?.status === 'OPTIMAL' ? 'tone-ok' : 'tone-warn'}`}>
            {dr ? `${dr.rto_seconds}s RTO` : 'POLLING…'}
          </b>
          {dr ? (
            <div style={{ marginTop: 12 }}>
              <div className="sre-metric-row">
                <span className="muted">Active / Standby</span>
                <code>{dr.active_region} / {dr.secondary_region}</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Recovery Time (RTO)</span>
                <code>{dr.rto_seconds}s (SLA &le; 5.0s)</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Data Loss (RPO)</span>
                <code>{dr.rpo_seconds}s (Transactional)</code>
              </div>
            </div>
          ) : <p className="muted small">Awaiting DR orchestrator status.</p>}
          <SourceTag ds={dr?.data_source} />
        </Tilt>

        <Tilt className="card" max={8}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span className="card__k">Adaptive Drift (EWMA / CUSUM)</span>
            {drift && <Chip tone={drift.drift_detected ? 'bad' : 'ok'}>{drift.status}</Chip>}
          </div>
          <b className={`syslink__word ${drift?.drift_detected ? 'tone-bad' : 'tone-ok'}`}>
            {drift ? (drift.current_ewma === null ? 'NO DATA' : `${drift.current_ewma}ms EWMA`) : 'POLLING…'}
          </b>
          {drift ? (
            <div style={{ marginTop: 12 }}>
              <div className="sre-metric-row">
                <span className="muted">Current Observation</span>
                <code>{drift.observed_value} ms</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">CUSUM S-High Stat</span>
                <code>{drift.cusum_high_statistic} (h={drift.decision_threshold_h})</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">CUSUM S-Low Stat</span>
                <code>{drift.cusum_low_statistic}</code>
              </div>
              <div className="sre-metric-row">
                <span className="muted">Micro-Regression Status</span>
                <span className={drift.drift_detected ? 'tone-bad' : 'tone-ok'}>
                  {drift.drift_detected ? 'DRIFT BREACH' : 'STABLE BASELINE'}
                </span>
              </div>
              <p className="muted small" style={{ marginTop: 8 }}>{drift.action}</p>
            </div>
          ) : <p className="muted small">Awaiting statistical drift detector.</p>}
          <SourceTag ds={drift?.data_source} />
        </Tilt>
      </div>
    </section>
  );
}

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
          <StateStorage />
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

      <SREOperations />

      <section className="sec sec--tight">
        <SecHead num="C" title="Authority">Each fact has exactly one source allowed to establish it. This console only displays what that source recorded.</SecHead>
        <ol className="authority">
          {AUTHORITY.map(([fact, who], i) => (
            <li key={fact} data-reveal style={{ ['--i' as string]: i }} className={who.includes('advisory') ? 'is-ai' : fact === 'RECOVERED' ? 'is-proof' : ''}>
              <span className="authority__fact">{fact}</span><span className="authority__arrow" aria-hidden="true">⟶</span><span className="authority__who">{who}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="sec sec--tight">
        <SecHead num="D" title="The loop, wired">Eleven steps, who acts, who owns it, and how many matching events this console has seen{source === 'demo' ? ' in the scripted scenario' : ''}.</SecHead>
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

