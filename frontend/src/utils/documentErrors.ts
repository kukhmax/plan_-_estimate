import { ApiError } from '../api/http';

/** The words for a document problem: by the stable code the backend sent, never by its English message. */
export function documentErrorText(
  errors: Record<string, string>,
  error: unknown,
  params: Record<string, string | number> = {},
): string {
  const code = error instanceof ApiError ? error.code : typeof error === 'string' ? error : undefined;
  const detail = error instanceof ApiError && error.detail && typeof error.detail === 'object' ? (error.detail as { details?: Record<string, unknown> }).details : undefined;
  const merged: Record<string, unknown> = { ...(detail ?? {}), ...params };
  const template = (code && errors[code]) || errors.UNKNOWN;
  return template.replace(/\{(\w+)\}/g, (match, key: string) => (key in merged ? String(merged[key]) : match));
}
