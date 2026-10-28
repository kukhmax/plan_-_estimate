// Telegram haptic feedback where the WebApp runtime offers it; silently nothing in a plain browser / older clients.
export function hapticNotify(type: 'success' | 'error' | 'warning'): void {
  window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.(type);
}

/** A light tap: something was picked up / moved over a new place (the drag of a list row). */
export function hapticSelect(kind: 'pick' | 'step'): void {
  const haptics = window.Telegram?.WebApp?.HapticFeedback;
  if (kind === 'pick') haptics?.impactOccurred?.('medium');
  else haptics?.selectionChanged?.();
}
