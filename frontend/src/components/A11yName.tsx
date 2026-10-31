/**
 * Owner 2026-10-31 (item 9): a name a screen reader can read. The technical `aria-label` of a control ("open-room-<id>") stays for the
 * tests and the scripts; the control points at this text with `aria-labelledby`, which wins over `aria-label` in the accessible name.
 * The span is empty and `hidden` (the name is its own `aria-label`): it adds no text to the page, is never shown and never read twice --
 * only through the reference.
 */
export function a11yId(kind: string, key: string): string {
  return `pe-name-${kind}-${key.replace(/[^A-Za-z0-9_-]/g, '_')}`;
}

export function A11yName({ id, text }: { id: string; text: string }) {
  return (
    <span id={id} hidden aria-label={text} />
  );
}
