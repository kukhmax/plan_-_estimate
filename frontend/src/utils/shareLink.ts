/**
 * Send a link with its description in a messenger: the description FIRST, the link under it ("Wycena do wglądu i zatwierdzenia:" and then the address), which is the order a reader
 * expects. The share window of Telegram (`t.me/share/url`) always puts its `url` before its `text`, so the description goes into `url` and the address into `text`; the share sheet of a
 * phone gets one text with the two lines. Without either, `copy` is called (the address alone goes to the clipboard).
 */
export function shareLink(link: string, description: string, copy: () => void): void {
  const telegram = window.Telegram?.WebApp;
  if (telegram?.openTelegramLink) {
    telegram.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(description)}&text=${encodeURIComponent(link)}`);
  } else if (typeof navigator.share === 'function') {
    void navigator.share({ text: `${description}\n${link}` }).catch(() => undefined);
  } else {
    copy();
  }
}
