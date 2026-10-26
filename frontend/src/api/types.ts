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

export interface CandidateFixView {
  candidate_id: string;
  title: string;
  author_model: string;
  approach: string;
  status: 'SELECTED' | 'REJECTED';
  rejection_reason?: string | null;
  trust_score: number;
  target_files: string[];
  diff_patch: string;
  gate_results: {
    integrity_gate: string;
    holdout_gate: string;
    regression_proof: string;
    blocking_findings?: GateFinding[];
  };
}

export interface TrustScoreView {
  trust_score: number;
  max_score: number;
  rating: string;
  recommendation: string;
  deductions: { factor: string; points: number; reason: string }[];
  bonuses: { factor: string; points: number; reason: string }[];
  ai_explanation: string;
  governance_rule: string;
}

export interface HoldoutGateView {
  gate: string;
  verdict: string;
  elapsed_ms: number;
  invariants_tested: number;
  invariants_passed: number;
  invariants: { invariant_id: string; name: string; status: string; confidential: boolean }[];
  security_note: string;
}

export interface SaboteurAttackResult {
  strategy_id: string;
  name: string;
  description: string;
  target_file: string;
  intended_evasion: string;
  gate_verdict: string;
  blocked: boolean;
  blocking_findings_count: number;
  findings: GateFinding[];
  diff_patch: string;
  live_status: string;
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
  trust_score?: TrustScoreView;
  candidates?: CandidateFixView[];
  holdout_gate?: HoldoutGateView;
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
  /** The backend recorded this event but refused it (bad source, illegal transition…). It proves nothing. */
  rejected?: { code: string; message: string };
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

// ==============================================================================
// Principal SRE, OPA Rego, eBPF & Multi-Region DR Telemetry Contracts
// ==============================================================================

export interface SRECompositeHealth {
  health_score: number;
  status: 'PASS' | 'WARN' | 'FAIL';
  error_budget: {
    burn_rate: number;
    alert_tier: 'NORMAL' | 'TICKET' | 'PAGE_SEVERITY_2' | 'PAGE_SEVERITY_1';
    hours_to_exhaustion: number;
    recommended_action?: string;
  };
  hypothesis_testing: {
    p_value: number;
    is_significant: boolean;
    interpretation?: string;
  };
  latency_iqr?: {
    median: number;
    q1: number;
    q3: number;
    iqr: number;
    outlier_threshold: number;
  };
  statistical_anomalies_detected?: number;
}

export interface OPAComplianceReport {
  timestamp: string;
  policy_package: string;
  allow: boolean;
  compliance_score: number;
  total_guardrails: number;
  violations_count: number;
  violations: string[];
  status: 'APPROVED' | 'REJECTED_BY_POLICY_GATE';
}

export interface EBPFTelemetryReport {
  timestamp: string;
  samples_collected: number;
  mean_transport_health_score: number;
  status: 'PASS' | 'FAIL';
  latency_decomposition_averages_ms: {
    dns_resolution: number;
    tcp_handshake: number;
    tls_handshake: number;
    server_ttfb: number;
  };
  kernel_socket_aggregates: {
    total_tcp_retransmits: number;
    total_syn_queue_drops: number;
    retransmission_rate: number;
  };
}

export interface DisasterRecoveryStatus {
  timestamp: string;
  primary_region: string;
  secondary_region: string;
  active_region: string;
  rto_seconds: number;
  rpo_seconds: number;
  status: 'OPTIMAL' | 'DEGRADED';
}

export interface S3StorageStatus {
  storage_type: string;
  bucket_name: string | null;
  region: string | null;
  prefix: string;
  s3_connected: boolean;
  encryption: {
    algorithm: string | null;
    kms_key_id: string | null;
    bucket_key_enabled: boolean;
  };
  distributed_locking: {
    table_name: string;
    status: string;
  };
  versioning_enabled: boolean;
  last_sync_timestamp: string | null;
  total_snapshots_recorded: number;
  health: string;
}

export interface AdaptiveDriftStatus {
  timestamp: string;
  observed_value: number;
  current_ewma: number;
  cusum_high_statistic: number;
  cusum_low_statistic: number;
  decision_threshold_h: number;
  drift_detected: boolean;
  status: string;
  action: string;
}

export interface DiffRiskReport {
  recommended_strategy: string;
  diff_risk: {
    risk_score: number;
    max_risk: number;
    risk_tier: string;
    is_ai_authored: boolean;
    risk_factors: { factor: string; points: number; details: string }[];
    adaptive_rollout_steps: { traffic_percent: number; wait_seconds: number; evaluator_required: boolean; description: string }[];
    rollout_steps_summary: string;
    rationale: string;
  };
  rationale: string;
  strategies: Record<string, {
    name: string;
    recommended: boolean;
    blast_radius: string;
    rollback_speed_seconds: number;
    zero_downtime: boolean;
    cost_overhead: string;
    description: string;
    rollout_steps?: string;
  }>;
}

export interface ShadowReplayReport {
  specification: string;
  incident_id: string;
  candidate_revision: string;
  timestamp: string;
  elapsed_ms: number;
  verdict: 'PASS' | 'FAIL';
  summary: {
    total_replayed_requests: number;
    baseline_failures: number;
    baseline_error_rate_pct: number;
    candidate_failures: number;
    candidate_error_rate_pct: number;
    error_reduction_delta_pct: number;
    shadow_parity_score_pct: number;
  };
  replayed_samples: {
    request_id: string;
    path: string;
    method: string;
    trigger_cause: string;
    baseline_status: number;
    candidate_status: number;
    mitigated: boolean;
  }[];
  conclusion: string;
}

export interface MeasuredCarbonReport {
  specification: string;
  service_name: string;
  region: string;
  grid_name: string;
  carbon_free_energy_pct: number;
  sci_score: number;
  sci_unit: string;
  per_request_gco2: number;
  sci_ceiling_target: number;
  measurement_mode: string;
  is_measured: boolean;
  telemetry_source: string;
  verdict: string;
  measured_telemetry?: {
    cpu_seconds: number;
    memory_mb_seconds: number;
    request_count: number;
    network_bytes: number;
  };
  components: {
    energy_consumed_kwh_E: number;
    grid_marginal_intensity_I: number;
    operational_emissions_gco2: number;
    embodied_emissions_gco2_M: number;
    total_emissions_gco2: number;
    functional_units_R: number;
  };
  recommendations: string[];
}

export interface PostmortemBundle {
  incident_id: string;
  title: string;
  generated_at: string;
  sha256: string;
  format: string;
  markdown: string;
  mr_title: string;
  mr_labels: string[];
}





