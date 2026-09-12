export function formatMetric(
  value: string | number | null | undefined,
  decimals = 2,
): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = typeof value === 'number' ? value : Number(value);
  if (Number.isNaN(num)) return '—';
  return num.toFixed(decimals);
}
