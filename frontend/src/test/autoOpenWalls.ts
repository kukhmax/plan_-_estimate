import { act, fireEvent } from '@testing-library/react';

/**
 * Wall cards are one-line rows until tapped (Stage 18G). Tests written before that about what is ON a wall card (Opcje, Badanie,
 * Realizacja, the photo section) open every wall the moment its row appears, as an owner's tap would; the behaviour of the rows
 * themselves is tested in SurfaceList.test.tsx and does not use this.
 */
export function installAutoOpenWalls(): () => void {
  const open = () => {
    const rows = Array.from(document.querySelectorAll<HTMLElement>('[aria-label^="surface-row-"][aria-expanded="false"]'));
    if (rows.length === 0) return;
    act(() => {
      for (const row of rows) fireEvent.click(row);
    });
  };
  const observer = new MutationObserver(open);
  observer.observe(document.body, { childList: true, subtree: true });
  return () => observer.disconnect();
}

/**
 * The calculation of the area of a wall (gross, openings, reveals) is folded behind a tap on the net area (usability U-7). Tests written
 * before that about those figures open it the moment the button appears, as an owner's tap would.
 */
export function installAutoOpenAreaDetails(): () => void {
  const open = () => {
    const buttons = Array.from(document.querySelectorAll<HTMLElement>('[aria-label^="area-details-"][aria-expanded="false"]'));
    if (buttons.length === 0) return;
    act(() => {
      for (const button of buttons) fireEvent.click(button);
    });
  };
  const observer = new MutationObserver(open);
  observer.observe(document.body, { childList: true, subtree: true });
  return () => observer.disconnect();
}
