import { Fragment, useEffect, useState } from 'react';
import {
  API_BASE, GITLAB_URL,
  getAdaptiveDriftStatus, getDisasterRecoveryStatus, getMeasuredCarbon, getEBPFTelemetry, getOPACompliance, getS3StorageStatus, getSRECompositeHealth,
} from '../api/client';
import { useSentinel } from '../api/source';
import type { AdaptiveDriftStatus, DataSource, MeasuredCarbonReport, DisasterRecoveryStatus, EBPFTelemetryReport, OPAComplianceReport, S3StorageStatus, SRECompositeHealth } from '../api/types';
import { useMission } from '../state/mission';
import { Badge, Empty, PageHead, Section, ago } from '../ui/kit';

const ENDPOINTS: [string, string][] = [
  ['healthz', '/api/v1/healthz'], ['status', '/api/v1/status'], ['releases', '/api/v1/releases'], ['incidents', '/api/v1/incidents'],
  ['events', '/api/v1/events'], ['incident', '/api/v1/incidents/{id}'], ['timeline', '/api/v1/incidents/{id}/timeline'], ['storage', '/api/v1/state/storage'],
];

/** The loop, and who acts at each step. */
const LOOP: [string, string, string][] = [
  ['Push to the default branch: build, test, scan, package', 'CI', 'pipeline.started'],
  ['Deploy the candidate with 0% traffic', 'CI', 'deploy.canary_started'],
  ['Probe candidate vs stable, step traffic 10 → 50 → 100%', 'Health evaluator', 'evaluator.verdict'],
  ['On a breach: all traffic back to known good, probe confirms', 'Evaluator + CI', 'rollback.completed'],
  ['Seal a redacted evidence bundle and open the incident', 'CI → backend', 'evidence.collected'],
  ['Investigate, write analysis.json, open a fix MR with a regression test', 'Duo flow (advisory)', 'repair.proposed'],
  ['Regression proof and Integrity Gate on the fix MR', 'Gate jobs', 'regression_proof.verdict'],
  ['All required jobs pass, the merge job merges', 'CI', 'merge.completed'],
  ['The merged fix goes through the canary again', 'CI + evaluator', 'redeploy.completed'],
  ['Post-redeploy evaluation passes, incident marked RECOVERED', 'Evaluator → backend', 'recovery.verified'],
];

/** Who is allowed to decide each fact. */
const AUTHORITY: [string, string][] = [
  ['Job status', 'GitLab'], ['Traffic split', 'Cloud Run, changed only through CI'], ['Health', 'The health evaluator'],
  ['Rollback happened', 'Rollback job plus a healthy post-rollback probe'], ['Investigation and repair', 'GitLab Duo flow — advisory only'],
  ['Regression verdict', 'The regression-proof job'], ['Test integrity', 'The Integrity Gate job'], ['Merge', 'Required CI jobs'],
  ['RECOVERED', 'The post-redeploy evaluator'], ['Incident record', 'Sentinel backend, from HMAC-signed CI events only'],
];

function Storage() {
  const { source } = useSentinel();
  const { now } = useMission();
  const [v, setV] = useState<S3StorageStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (source !== 'live') return;
    const ctrl = new AbortController();
    const read = () => getS3StorageStatus(ctrl.signal).then((x) => { setV(x); setErr(null); }).catch((e: Error) => setErr(e.message));
    read();
    const t = setInterval(read, 15_000);
    return () => { ctrl.abort(); clearInterval(t); };
  }, [source]);
  return (
    <div className="card">
      <div className="verdict"><h3>Incident state storage</h3>{v && <Badge tone={v.s3_connected ? 'ok' : 'mute'}>{v.s3_connected ? 'S3 connected' : 'local only'}</Badge>}</div>
      {source === 'demo' ? <p className="small muted">Not read in the demo scenario.</p> : !v ? <p className="small muted">{err ? `Not readable: ${err}` : 'Not read yet.'}</p> : (
        <p className="small" style={{ color: 'var(--ink-2)' }}>
          {v.s3_connected ? 'The backend reached its S3 bucket.' : 'No S3 connection; snapshots stay on the backend\'s local disk.'} {v.total_snapshots_recorded ?? 0} snapshots recorded{v.last_sync_timestamp ? `, last ${ago(v.last_sync_timestamp, now)}` : ''}.
          {v.bucket_name && <> Bucket <code>{v.bucket_name}</code>{v.region && ` (${v.region})`}.</>}
        </p>
      )}
    </div>
  );
}

type Row = [string, string | number | null | undefined];
const SOURCE_LABEL: Record<DataSource['kind'], string> = { measured: 'measured', derived: 'derived', reference: 'reference input', simulated: 'simulated' };

/** One extra panel. Its source label says where the numbers come from, so simulated values are never read as telemetry. */
function SimCard({ title, status, rows, ds }: { title: string; status?: string; rows: Row[] | null; ds?: DataSource }) {
  return (
    <div className="card">
      <div className="verdict"><h3>{title}</h3>{status && <Badge tone={status === 'NO_DATA' ? 'mute' : undefined}>{status.replace(/_/g, ' ')}</Badge>}</div>
      {rows ? <dl className="kv">{rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd className="mono">{v ?? '—'}</dd></Fragment>)}</dl> : <p className="small muted">No answer from the backend.</p>}
      {ds && <p className="small muted" style={{ marginTop: 10 }}><Badge tone={ds.kind === 'measured' ? 'ok' : ds.kind === 'derived' ? 'info' : 'warn'}>{SOURCE_LABEL[ds.kind] ?? ds.kind}</Badge> {ds.note}</p>}
    </div>
  );
}

function Simulated() {
  const { source } = useSentinel();
  const [open, setOpen] = useState(false);
  const [sre, setSre] = useState<SRECompositeHealth | null>(null);
  const [opa, setOpa] = useState<OPAComplianceReport | null>(null);
  const [ebpf, setEbpf] = useState<EBPFTelemetryReport | null>(null);
  const [dr, setDr] = useState<DisasterRecoveryStatus | null>(null);
  const [drift, setDrift] = useState<AdaptiveDriftStatus | null>(null);
  const [carbon, setCarbon] = useState<MeasuredCarbonReport | null>(null);
  useEffect(() => {
    if (!open || source !== 'live') return;
    const ctrl = new AbortController();
    getSRECompositeHealth(ctrl.signal).then(setSre).catch(() => {});
    getOPACompliance(ctrl.signal).then(setOpa).catch(() => {});
    getEBPFTelemetry(ctrl.signal).then(setEbpf).catch(() => {});
    getDisasterRecoveryStatus(ctrl.signal).then(setDr).catch(() => {});
    getAdaptiveDriftStatus(ctrl.signal).then(setDrift).catch(() => {});
    getMeasuredCarbon(ctrl.signal).then(setCarbon).catch(() => {});
    return () => ctrl.abort();
  }, [open, source]);
  const sreRows: Row[] | null = sre && (sre.health_score === null || !sre.error_budget || !sre.hypothesis_testing
    ? [['score', 'no evaluator measurement yet']]
    : [['score', sre.health_score], ['burn rate', `${sre.error_budget.burn_rate}× (${sre.error_budget.alert_tier})`], ['Mann-Whitney p', sre.hypothesis_testing.p_value]]);
  return (
    <details className="sim" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Extra telemetry <Badge tone="warn">not part of the loop</Badge></summary>
      <div className="sim__body stack">
        <p className="note note--warn">Each panel says where its numbers come from. Only panels marked “measured” read the running service; the rest are derived, reference inputs or simulations. Health, rollback, merge and recovery are decided only by the evaluator, the gates and CI.</p>
        {source === 'demo' ? <p className="small muted">Not shown in the demo scenario.</p> : (
          <div className="grid g2">
            <SimCard title="Error budget and rank-sum test" status={sre?.status} rows={sreRows} ds={sre?.data_source} />
            <SimCard title="OPA policy check" status={opa?.status} rows={opa && [['package', opa.policy_package], ['compliance', `${opa.compliance_score}%`], ['violations', opa.violations_count]]} ds={opa?.data_source} />
            <SimCard title="eBPF socket traces" status={ebpf?.status} rows={ebpf && [['transport score', ebpf.mean_transport_health_score], ['server TTFB', `${ebpf.latency_decomposition_averages_ms.server_ttfb} ms`], ['TCP retransmits', ebpf.kernel_socket_aggregates.total_tcp_retransmits]]} ds={ebpf?.data_source} />
            <SimCard title="Disaster-recovery drill" status={dr?.status} rows={dr && [['regions', `${dr.primary_region} → ${dr.secondary_region}`], ['RTO', `${dr.rto_seconds}s`], ['RPO', `${dr.rpo_seconds}s`]]} ds={dr?.data_source} />
            <SimCard title="Latency drift (CUSUM)" status={drift?.status} rows={drift && [['observed', drift.observed_value], ['EWMA', drift.current_ewma], ['drift', drift.drift_detected ? 'yes' : 'no']]} ds={drift?.data_source} />
            <SimCard title="SCI carbon intensity" status={carbon?.verdict} rows={carbon && [['SCI', `${carbon.sci_score} ${carbon.sci_unit}`], ['grid', `${carbon.grid_name} (${carbon.carbon_free_energy_pct}% CFE)`], ['mode', carbon.measurement_mode]]} ds={carbon ? { kind: carbon.is_measured ? 'measured' : 'simulated', note: carbon.telemetry_source } : undefined} />
          </div>
        )}
      </div>
    </details>
  );
}

export default function System() {
  const { source, snap, connected, error, endpoints } = useSentinel();
  const { now } = useMission();
  const hz = snap.healthz;
  return (
    <>
      <PageHead eyebrow="System" title="How Mission Control is wired">
        Where the data comes from, who is allowed to decide each fact, and what the loop does at every step.
      </PageHead>

      <Section title="API link">
        <div className="grid g2">
          <div className="card">
            <div className="verdict"><h3>Sentinel API</h3>
              <Badge tone={source === 'demo' ? 'warn' : connected ? 'ok' : connected === false ? 'bad' : 'mute'}>{source === 'demo' ? 'demo' : connected ? 'connected' : connected === false ? 'offline' : 'connecting'}</Badge>
            </div>
            <dl className="kv">
              <dt>Base URL</dt><dd className="mono">{API_BASE || 'same origin (/api, proxied in dev)'}</dd>
              <dt>Service</dt><dd>{hz ? `${hz.service ?? 'sentinel'} ${hz.version ?? ''} · ${hz.status}` : '—'}</dd>
              <dt>GitLab project</dt><dd>{GITLAB_URL ? <a href={GITLAB_URL} target="_blank" rel="noreferrer">{GITLAB_URL.replace(/^https?:\/\//, '')} ↗</a> : <span className="muted">not configured (VITE_GITLAB_PROJECT_URL)</span>}</dd>
              {error && source === 'live' && <><dt>Last error</dt><dd style={{ color: 'var(--bad)' }}>{error}</dd></>}
            </dl>
            <p className="small muted" style={{ marginTop: 10 }}>The browser sends no credentials. Anything that changes state is signed by CI with HMAC.</p>
          </div>
          <Storage />
        </div>
      </Section>

      <Section title="Endpoints" note="What this page has read so far.">
        {source === 'demo' ? <Empty title="The demo scenario does not call the API." /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Endpoint</th><th>Status</th><th className="num">Latency</th><th className="num">Last read</th></tr></thead>
              <tbody>{ENDPOINTS.map(([k, path]) => {
                const e = endpoints[k];
                return (
                  <tr key={k}>
                    <td className="mono small">{path}</td>
                    <td>{!e ? <span className="muted small">not called</span> : e.ok ? <Badge tone="ok">ok</Badge> : <Badge tone="bad">{e.error ?? 'failed'}</Badge>}</td>
                    <td className="num small">{e?.ms != null ? `${e.ms} ms` : '—'}</td>
                    <td className="num small">{e?.at ? ago(e.at, now) : '—'}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Who decides what" note="No fact is taken from the AI or from this page.">
        <div className="table-wrap">
          <table><tbody>{AUTHORITY.map(([k, v]) => <tr key={k}><td style={{ width: '34%' }}>{k}</td><td style={{ color: 'var(--ink-2)' }}>{v}</td></tr>)}</tbody></table>
        </div>
      </Section>

      <Section title="The loop, step by step">
        <div className="table-wrap">
          <table>
            <thead><tr><th>#</th><th>Step</th><th>Who acts</th><th>Event</th></tr></thead>
            <tbody>{LOOP.map(([what, who, ev], i) => (
              <tr key={ev}><td className="mono small muted">{String(i + 1).padStart(2, '0')}</td><td>{what}</td><td className="small">{who.includes('Duo') ? <Badge tone="ai">{who}</Badge> : who}</td><td className="mono small">{ev}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </Section>

      <Section title="Extras">
        <Simulated />
      </Section>
    </>
  );
}
