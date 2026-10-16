/**
 * The preview of an area for a record only the phone knows (owner decision Q5 (b)): the typed width × height, marked "~" on the screen
 * (the server's own number replaces it after the synchronisation). `null` when a side is missing or is not a number.
 */
export function previewArea(width: unknown, height: unknown): string | null {
  const w = typeof width === 'string' || typeof width === 'number' ? Number(width) : NaN;
  const h = typeof height === 'string' || typeof height === 'number' ? Number(height) : NaN;
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
  return (w * h).toFixed(2);
}
