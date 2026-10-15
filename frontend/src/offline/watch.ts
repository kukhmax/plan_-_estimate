import { API_BASE } from '../api/http';
import { getConnectionState, reportNetworkFailure, reportNetworkSuccess } from './connection';

export const PROBE_INTERVAL_MS = 15_000;
const PROBE_TIMEOUT_MS = 5_000;

/** One look at the server: `/api/health`, no copy kept, no token. */
export async function probeServer(): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}/api/health`, { signal: controller.signal, cache: 'no-store' });
    if (response.ok) {
      reportNetworkSuccess();
      return true;
    }
    return false;
  } catch {
    reportNetworkFailure();
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Starts watching the connection: the browser's events, and a look at the server every 15 s while it cannot be reached
 * (so the "no connection" strip goes away by itself when the signal comes back). Returns the function that stops it.
 */
export function startConnectionWatch(probe: () => Promise<boolean> = probeServer): () => void {
  const onOffline = () => reportNetworkFailure();
  const onOnline = () => void probe();
  window.addEventListener('offline', onOffline);
  window.addEventListener('online', onOnline);
  const timer = setInterval(() => {
    if (getConnectionState().offline) void probe();
  }, PROBE_INTERVAL_MS);
  return () => {
    window.removeEventListener('offline', onOffline);
    window.removeEventListener('online', onOnline);
    clearInterval(timer);
  };
}
