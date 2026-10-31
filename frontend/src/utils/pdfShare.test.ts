/** Owner 2026-10-31: the PDF in the application -- Telegram's own download sheet, the phone's share sheet, or a new tab. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { shareOrDownloadPdf } from './pdfShare';

const LINK = { url: '/api/public/files/abc.def', file_name: 'KOSZ-2026-10-08-1953.pdf' };

afterEach(() => {
  delete window.Telegram;
  vi.restoreAllMocks();
});

describe('shareOrDownloadPdf', () => {
  it('hands the absolute address to Telegram when it can download a file', async () => {
    const downloadFile = vi.fn();
    window.Telegram = { WebApp: { downloadFile } } as unknown as typeof window.Telegram;
    expect(await shareOrDownloadPdf(LINK)).toBe('telegram');
    expect(downloadFile).toHaveBeenCalledWith({ url: `${window.location.origin}/api/public/files/abc.def`, file_name: LINK.file_name });
  });

  it('gives the file to the share sheet of the phone outside Telegram', async () => {
    const share = vi.fn(async () => undefined);
    Object.assign(navigator, { share, canShare: () => true });
    vi.spyOn(window, 'fetch').mockResolvedValue(new Response(new Blob(['%PDF']), { status: 200 }));
    expect(await shareOrDownloadPdf(LINK)).toBe('shared');
    const [data] = share.mock.calls[0] as unknown as [{ files: File[] }];
    expect(data.files[0].name).toBe(LINK.file_name);
    Object.assign(navigator, { share: undefined, canShare: undefined });
  });

  it('opens the PDF in a new tab when neither can', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    expect(await shareOrDownloadPdf(LINK)).toBe('opened');
    expect(open).toHaveBeenCalledWith(`${window.location.origin}/api/public/files/abc.def`, '_blank', 'noopener');
  });
});
