import { useState } from 'react';
import type { FileLink } from '../api/documents';
import { useI18n } from '../hooks/useI18n';
import { shareOrDownloadPdf } from '../utils/pdfShare';
import { Ico } from './Ico';

/** Owner 2026-10-31: "Udostępnij / pobierz PDF" -- the file in the application, besides the copy the bot sends to the chat. */
export function PdfShareButton({ label, link }: { label: string; link: () => Promise<FileLink> }) {
  const { t } = useI18n();
  const text = t.documents;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const run = async () => {
    if (busy) return;
    setBusy(true);
    setError(false);
    try {
      await shareOrDownloadPdf(await link());
    } catch (err) {
      // a share sheet the owner closed is not a failure
      if (!(err instanceof DOMException && err.name === 'AbortError')) setError(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-1">
      <button
        type="button"
        aria-label={label}
        disabled={busy}
        onClick={() => void run()}
        className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-slate-300 pe-surface text-slate-800 disabled:opacity-60 break-words"
      >
        <Ico>{busy ? '⏳' : '📤'}</Ico>{text.share_pdf}
      </button>
      {error && <p role="alert" className="text-xs text-red-700 break-words">{text.share_failed}</p>}
    </div>
  );
}
