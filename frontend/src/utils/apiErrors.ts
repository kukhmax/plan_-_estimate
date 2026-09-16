import { ApiError } from '../api/http';

/** Shape of the i18n `errors` block consumed by localizeApiError. */
export interface ApiErrorsI18n {
  errors: Record<string, string>;
}

// Localize known Pydantic validation phrases while preserving unknown structured detail.
const PYDANTIC_MESSAGE_PATTERNS: Array<{ pattern: RegExp; key: string }> = [
  { pattern: /decimal places/i, key: 'validation_decimal_places' },
  { pattern: /greater than or equal to 1/i, key: 'validation_greater_than_equal' },
  { pattern: /greater than 0/i, key: 'validation_greater_than' },
  { pattern: /should be an integer|a valid integer/i, key: 'validation_integer' },
  { pattern: /field required/i, key: 'validation_required' },
];

function pydanticKey(message: string): string | undefined {
  for (const entry of PYDANTIC_MESSAGE_PATTERNS) {
    if (entry.pattern.test(message)) return entry.key;
  }
  return undefined;
}

export function localizeApiError(error: unknown, t: ApiErrorsI18n): string {
  if (error instanceof ApiError) {
    const fallback = t.errors.validation_failed ?? '';
    if (error.code && t.errors[error.code]) return t.errors[error.code];
    const key = pydanticKey(error.message);
    if (key && t.errors[key]) return t.errors[key];
    if (error.status === 422 && error.message === 'Request failed (422)') return fallback;
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return t.errors.validation_failed ?? 'Request failed';
}