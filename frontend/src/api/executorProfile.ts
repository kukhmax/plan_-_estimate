import { ExecutorProfile, ExecutorProfilePayload, ExecutorProfileResponse } from '../types/executorProfile';
import { apiRequest } from './http';

export async function fetchExecutorProfile(): Promise<ExecutorProfile | null> {
  const response = await apiRequest<ExecutorProfileResponse>('/api/executor-profile');
  return response.profile;
}

export function saveExecutorProfile(payload: ExecutorProfilePayload): Promise<ExecutorProfile> {
  return apiRequest<ExecutorProfile>('/api/executor-profile', { method: 'PUT', body: JSON.stringify(payload) });
}

/** Field → error code from a 422 EXECUTOR_PROFILE_INVALID; {} for any other error. */
export function profileFieldErrors(detail: unknown): Record<string, string> {
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return {};
  const { code, fields } = detail as { code?: unknown; fields?: unknown };
  if (code !== 'EXECUTOR_PROFILE_INVALID' || !fields || typeof fields !== 'object' || Array.isArray(fields)) return {};
  const result: Record<string, string> = {};
  for (const [field, value] of Object.entries(fields)) {
    if (typeof value === 'string') result[field] = value;
  }
  return result;
}
