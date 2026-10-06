// Telegram haptic feedback where the WebApp runtime offers it; silently nothing in a plain browser / older clients.
export function hapticNotify(type: 'success' | 'error' | 'warning'): void {
  window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.(type);
}
