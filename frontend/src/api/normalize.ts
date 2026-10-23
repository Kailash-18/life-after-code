/**
 * Tolerant readers for API payloads. They never invent values: anything missing
 * stays missing and the UI shows it as missing.
 *
 * They accept both the contract shapes (openapi.yaml, analysis.schema.json) and the
 * shapes the current backend skeleton returns (raw event records with received_at /
 * job_id / artifact_url), so the UI keeps working while the backend catches up.
 */
import type { Analysis, GateFinding, GateResult, Healthz, Incident, IncidentDetail, RecoveryAttempt, Release, SystemStatus, TestResult, TimelineEvent } from './types';

type O = Record<string, unknown>;
const obj = (v: unknown): O => (v && typeof v === 'object' && !Array.isArray(v) ? (v as O) : {});
const str = (v: unknown): string | undefined => (typeof v === 'string' && v.length ? v : typeof v === 'number' ? String(v) : undefined);
const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' && Number.isFinite(+v) ? +v : undefined);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : Array.isArray(obj(v).items) ? (obj(v).items as unknown[]) : []);
const strs = (v: unknown): string[] => arr(v).map((x) => (typeof x === 'string' ? x : str(obj(x).text) ?? str(obj(x).message) ?? str(obj(x).description) ?? JSON.stringify(x)));

export function toRelease(v: unknown): Release | null {
  const o = obj(v);
  const id = str(o.id);
  if (!id) return null;
  return {
    id, version: str(o.version) ?? id, commit_sha: str(o.commit_sha) ?? '', status: str(o.status) ?? 'UNKNOWN',
    known_good: o.known_good === true, created_at: str(o.created_at) ?? '', revision_name: str(o.revision_name),
    pipeline_id: str(o.pipeline_id), image_digest: str(o.image_digest),
  };
}
export const toReleases = (v: unknown) => arr(v).map(toRelease).filter((r): r is Release => !!r)
  .sort((a, b) => (Date.parse(a.created_at) || 0) - (Date.parse(b.created_at) || 0));

export function toIncident(v: unknown): Incident | null {
  const o = obj(v);
  const id = str(o.id);
  if (!id) return null;
  return {
    id, release_id: str(o.release_id) ?? '', detected_at: str(o.detected_at) ?? '', status: str(o.status) ?? 'UNKNOWN',
    breached_thresholds: strs(o.breached_thresholds), evidence_bundle_ref: str(o.evidence_bundle_ref), evidence_sha256: str(o.evidence_sha256),
  };
}
export const toIncidents = (v: unknown) => arr(v).map(toIncident).filter((i): i is Incident => !!i)
  .sort((a, b) => (Date.parse(b.detected_at) || 0) - (Date.parse(a.detected_at) || 0));

function toAnalysis(v: unknown): Analysis | undefined {
  if (!v || typeof v !== 'object') return undefined;
  const o = obj(v);
  const sc = o.suspected_change;
  const rts = obj(o.regression_test_strategy);
  return {
    outcome: str(o.outcome),
    facts: arr(o.facts).map((f) => (typeof f === 'string' ? { text: f } : {
      text: str(obj(f).fact) ?? str(obj(f).text) ?? str(obj(f).claim) ?? '',
      ref: str(obj(f).evidence_ref) ?? str(obj(f).ref),
    })).filter((f) => f.text),
    hypotheses: arr(o.hypotheses).map((h) => (typeof h === 'string' ? { text: h } : {
      text: str(obj(h).hypothesis) ?? str(obj(h).text) ?? str(obj(h).statement) ?? '',
      confidence: str(obj(h).confidence), rationale: str(obj(h).rationale),
    })).filter((h) => h.text),
    missing_evidence: strs(o.missing_evidence),
    suspected_change: typeof sc === 'string' ? { raw: sc } : sc && typeof sc === 'object'
      ? { commit_sha: str(obj(sc).commit_sha), file_path: str(obj(sc).file_path), line_range: str(obj(sc).line_range), reason: str(obj(sc).reason) }
      : undefined,
    proposed_fix: str(o.proposed_fix_summary) ?? str(o.proposed_fix),
    regression_test_file: str(rts.test_file) ?? str(o.regression_test_file),
    expected_failure_type: str(rts.expected_failure_type),
    file_ref: str(o.file_ref),
  };
}

function toFindings(v: unknown): GateFinding[] {
  return arr(v).map((f) => (typeof f === 'string'
    ? (/^RULE_\d+[A-Z0-9_]*$/.test(f.trim())
      ? { rule_id: f.trim(), message: 'Only the rule id was reported; the full finding is in the gate report.' }
      : { message: f, rule_id: f.match(/RULE_\d+[A-Z0-9_]*/)?.[0] })
    : { message: str(obj(f).message) ?? str(obj(f).details) ?? JSON.stringify(f), rule_id: str(obj(f).rule_id), severity: str(obj(f).severity), file: str(obj(f).file) }));
}

function toAttempt(v: unknown): RecoveryAttempt {
  const o = obj(v);
  return {
    id: str(o.id) ?? '', attempt_no: num(o.attempt_no) ?? 1, state: str(o.state) ?? '',
    flow_session_id: str(o.flow_session_id), mr_iid: num(o.mr_iid), fix_sha: str(o.fix_sha),
    failure_reason: str(o.failure_reason), deadline_at: str(o.deadline_at), analysis: toAnalysis(o.analysis),
    test_results: arr(o.test_results).map((t): TestResult => {
      const x = obj(t);
      return { id: str(x.id) ?? '', kind: str(x.kind) ?? '', sha: str(x.sha) ?? '', outcome: str(x.outcome) ?? '', failure_type: str(x.failure_type), junit_ref: str(x.junit_ref) };
    }),
    gate_results: arr(o.gate_results).map((g): GateResult => {
      const x = obj(g);
      return { id: str(x.id) ?? str(x.gate) ?? '', gate: str(x.gate) ?? '', verdict: (str(x.verdict) ?? '').toLowerCase(), findings: toFindings(x.findings), report_ref: str(x.report_ref) };
    }),
  };
}

export function toIncidentDetail(v: unknown): IncidentDetail | null {
  const base = toIncident(v);
  if (!base) return null;
  return { ...base, recovery_attempts: arr(obj(v).recovery_attempts).map(toAttempt).sort((a, b) => a.attempt_no - b.attempt_no) };
}

export function toTimeline(v: unknown): TimelineEvent[] {
  return arr(v)
    .map((e): TimelineEvent | null => {
      const o = obj(e);
      const at = str(o.at) ?? str(o.sent_at) ?? str(o.received_at);
      if (!at) return null;
      const data = obj(o.data);
      return {
        id: str(o.id) ?? `${str(o.type)}-${at}`, type: str(o.type) ?? 'event', source: str(o.source) ?? 'unknown source',
        job: str(o.source_job_id) ?? str(o.job_id), pipeline_id: str(o.pipeline_id), commit_sha: str(o.commit_sha),
        release_id: str(o.release_id), incident_id: str(o.incident_id) ?? (str(o.entity_type) === 'Incident' ? str(o.entity_id) : undefined),
        at, summary: str(o.summary) ?? str(data.summary), evidence_url: str(o.evidence_url) ?? str(o.artifact_url), data,
      };
    })
    .filter((e): e is TimelineEvent => !!e)
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
}

export function toStatus(v: unknown): SystemStatus {
  const o = obj(v);
  const split = obj(o.traffic_split);
  const health = obj(o.system_health);
  const sp = num(split.stable_percent), cp = num(split.candidate_percent);
  const er = num(health.error_rate), p95 = num(health.p95_ms);
  return {
    current_release: toRelease(o.current_release),
    candidate_release: toRelease(o.candidate_release),
    traffic_split: sp !== undefined && cp !== undefined ? { stable_percent: sp, candidate_percent: cp } : null,
    system_health: er !== undefined && p95 !== undefined ? { error_rate: er, p95_ms: p95, healthy: health.healthy === true } : null,
    active_incident: toIncident(o.active_incident),
  };
}

export function toHealthz(v: unknown): Healthz {
  const o = obj(v);
  return { status: str(o.status) ?? 'unknown', service: str(o.service), version: str(o.version) };
}
