import type {
  DisasterRecoveryStatus,
  EBPFTelemetryReport,
  OPAComplianceReport,
  S3StorageStatus,
  SRECompositeHealth,
} from './types';

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? '';
export const GITLAB_URL = (import.meta.env.VITE_GITLAB_PROJECT_URL as string | undefined)?.replace(/\/$/, '') ?? '';

/*
 * Mission Control is read-only and the backend's read API is unauthenticated, so the browser sends
 * no credentials. A key compiled into a browser bundle is public anyway; anything that needs a
 * secret (event ingestion, state changes) belongs to CI, which signs its requests with HMAC.
 */

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function getJSON(path: string, signal?: AbortSignal): Promise<unknown> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  signal?.addEventListener('abort', () => ctrl.abort());
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: ctrl.signal, headers: { Accept: 'application/json' } });
    if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
    const type = res.headers.get('content-type') ?? '';
    if (!type.includes('json')) throw new ApiError(502, 'The API did not answer with JSON');
    return await res.json();
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, ctrl.signal.aborted ? 'The API did not answer in time' : 'The API is unreachable');
  } finally {
    clearTimeout(timer);
  }
}

// ==============================================================================
// Optional SRE telemetry readers. They return exactly what the backend says and
// throw when it does not answer — no stand-in values. (The backend does not serve
// /api/v1/sre/* yet.)
// ==============================================================================
export const getSRECompositeHealth = (signal?: AbortSignal) => getJSON('/api/v1/sre/health', signal) as Promise<SRECompositeHealth>;
export const getOPACompliance = (signal?: AbortSignal) => getJSON('/api/v1/sre/opa', signal) as Promise<OPAComplianceReport>;
export const getEBPFTelemetry = (signal?: AbortSignal) => getJSON('/api/v1/sre/ebpf', signal) as Promise<EBPFTelemetryReport>;
export const getDisasterRecoveryStatus = (signal?: AbortSignal) => getJSON('/api/v1/sre/dr', signal) as Promise<DisasterRecoveryStatus>;
export const getS3StorageStatus = (signal?: AbortSignal) => getJSON('/api/v1/state/storage', signal) as Promise<S3StorageStatus>;
