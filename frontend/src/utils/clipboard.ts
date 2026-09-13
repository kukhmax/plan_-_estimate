/**
 * Copy text to the clipboard with a safe fallback for Telegram WebView /
 * mobile browsers where the Clipboard API may be unavailable or rejected.
 * Never throws; returns whether the copy succeeded.
 */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to the legacy input-based path.
    }
  }
  return legacyCopy(text);
}

function legacyCopy(text: string): boolean {
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    area.style.opacity = '0';
    document.body.appendChild(area);
    const selection = window.getSelection?.() ?? document.getSelection?.();
    const previousRange =
      selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
    area.select();
    const ok = document.execCommand?.('copy') ?? false;
    area.remove();
    if (ok && selection && previousRange) {
      selection.removeAllRanges();
      selection.addRange(previousRange);
    }
    return ok;
  } catch {
    return false;
  }
}