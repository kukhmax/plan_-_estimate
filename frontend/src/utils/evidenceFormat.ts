/** Format a backend ISO timestamp/date as DD.MM.YYYY for evidence lines.
 * Deterministic from the date part only — never locale/ICU-dependent. */
export function formatEvidenceDate(value: string | null | undefined): string {
  if (!value) return '—';
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!match) return '—';
  return `${match[3]}.${match[2]}.${match[1]}`;
}