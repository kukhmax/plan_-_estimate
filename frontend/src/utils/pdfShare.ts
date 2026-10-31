import type { FileLink } from '../api/documents';
import { API_BASE } from '../api/http';

export type PdfShareWay = 'telegram' | 'shared' | 'opened';

/**
 * Owner 2026-10-31: the PDF in the application, not only in the bot's chat. Inside Telegram the native "download" sheet takes the five-minute
 * address itself; elsewhere the phone's share sheet gets the file (send it to the client in WhatsApp, the e-mail...), and when neither is
 * there the PDF opens in a new tab, from where it is saved.
 */
export async function shareOrDownloadPdf(link: FileLink): Promise<PdfShareWay> {
  const address = new URL(link.url, API_BASE || window.location.origin).toString();
  const telegram = window.Telegram?.WebApp;
  if (telegram?.downloadFile) {
    telegram.downloadFile({ url: address, file_name: link.file_name });
    return 'telegram';
  }
  const nav = navigator as Navigator & { canShare?: (data: { files: File[] }) => boolean };
  if (typeof nav.share === 'function' && typeof nav.canShare === 'function') {
    const response = await fetch(address, { cache: 'no-store' });
    if (response.ok) {
      const file = new File([await response.blob()], link.file_name, { type: 'application/pdf' });
      if (nav.canShare({ files: [file] })) {
        await nav.share({ files: [file], title: link.file_name } as ShareData);
        return 'shared';
      }
    }
  }
  window.open(address, '_blank', 'noopener');
  return 'opened';
}
