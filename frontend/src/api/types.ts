/** Mirrors docs/contracts/openapi.yaml + analysis.schema.json + event.schema.json, after normalisation (./normalize.ts). */

export const RECOVERY_PATH = [
  'DETECTED', 'ROLLED_BACK', 'EVIDENCE_COLLECTED', 'INVESTIGATING', 'REPAIR_PROPOSED',
  'VERIFYING', 'MERGED', 'REDEPLOYING', 'RECOVERED',
] as const;
export type RecoveryStage = (typeof RECOVERY_PATH)[number];

export const TERMINAL_FAILURES = ['ROLLBACK_FAILED', 'INVESTIGATION_FAILED', 'VERIFICATION_FAILED', 'REDEPLOY_UNHEALTHY', 'TIMED_OUT', 'ESCALATED'] as const;

export interface Release {
  id: string;
  version: string;
  commit_sha: string;
  status: string;
  known_good: boolean;
  created_at: string;
  revision_name?: string;
  pipeline_id?: string;
  image_digest?: string;
}

export interface Incident {
  id: string;
  release_id: string;
  detected_at: string;
  status: string;
  breached_thresholds: string[];
  evidence_bundle_ref?: string;
  evidence_sha256?: string;
}

export interface TestResult { id: string; kind: string; sha: string; outcome: string; failure_type?: string; junit_ref?: string }
export interface GateFinding { rule_id?: string; severity?: string; file?: string; message: string }
export interface GateResult { id: string; gate: string; verdict: string; findings: GateFinding[]; report_ref?: string }

export interface Analysis {
  outcome?: 'fix_proposed' | 'no_fix_found' | string;
  facts: { text: string; ref?: string }[];
  hypotheses: { text: string; confidence?: string; rationale?: string }[];
  missing_evidence: string[];
  suspected_change?: { commit_sha?: string; file_path?: string; line_range?: string; reason?: string; raw?: string };
  proposed_fix?: string;
  regression_test_file?: string;
  expected_failure_type?: string;
  file_ref?: string;
}

export interface RecoveryAttempt {
  id: string;
  attempt_no: number;
  state: string;
  flow_session_id?: string;
  mr_iid?: number;
  fix_sha?: string;
  failure_reason?: string;
  deadline_at?: string;
  analysis?: Analysis;
  test_results: TestResult[];
  gate_results: GateResult[];
}

export interface IncidentDetail extends Incident { recovery_attempts: RecoveryAttempt[] }

/** One recorded event. `data` carries the measured values from event.schema.json (error_rate, p95_ms, traffic_percent, verdict, …). */
export interface TimelineEvent {
  id: string;
  type: string;
  source: string;
  job?: string;
  pipeline_id?: string;
  commit_sha?: string;
  release_id?: string;
  incident_id?: string;
  at: string;
  summary?: string;
  evidence_url?: string;
  data: Record<string, unknown>;
}

export interface SystemStatus {
  current_release: Release | null;
  candidate_release: Release | null;
  traffic_split: { stable_percent: number; candidate_percent: number } | null;
  system_health: { error_rate: number; p95_ms: number; healthy: boolean } | null;
  active_incident: Incident | null;
}

export interface Healthz { status: string; service?: string; version?: string }

/** Everything the interface reads, from one source (live API or the labelled demo). */
export interface Snapshot {
  status: SystemStatus | null;
  releases: Release[] | null;
  incidents: Incident[] | null;
  healthz: Healthz | null;
  /** Detail + timeline for the incident in focus (active, else most recent). */
  focus: IncidentDetail | null;
  timeline: TimelineEvent[] | null;
  /** Every incident detail fetched so far, by id. */
  details: Record<string, IncidentDetail>;
  /** Every incident timeline fetched so far, by incident id. */
  timelines: Record<string, TimelineEvent[]>;
  /** All known events, oldest first, de-duplicated. */
  events: TimelineEvent[];
}

export interface EndpointState { path: string; ok: boolean | null; at: number | null; ms: number | null; error?: string }
