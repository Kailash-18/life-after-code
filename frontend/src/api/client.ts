export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? '';
export const GITLAB_URL = (import.meta.env.VITE_GITLAB_PROJECT_URL as string | undefined)?.replace(/\/$/, '') ?? '';

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
