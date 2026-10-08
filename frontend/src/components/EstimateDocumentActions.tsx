import { useCallback, useEffect, useRef, useState } from 'react';
import { getDocument, issueEstimateDocument, previewEstimatePdf } from '../api/documents';
import { useI18n } from '../hooks/useI18n';
import type { EstimateStatusValue } from '../types/estimate';
import type { IssuedDocument } from '../types/document';
import { documentErrorText } from '../utils/documentErrors';

const POLL_MS = 2000;
const MAX_POLLS = 90; // three minutes: the server gives up on a document long before that

interface EstimateDocumentActionsProps {
  projectId: string;
  estimateId: string;
  status: EstimateStatusValue;
}

/**
 * Stage 15F.3 — "Wyślij PDF" for a finished estimate and "Podgląd PDF" for a draft. The PDF goes to the owner's chat with
 * the bot; a finished estimate gets a number and an entry in the journal, a draft is only a working preview.
 */
export function EstimateDocumentActions({ projectId, estimateId, status }: EstimateDocumentActionsProps) {
  const { t } = useI18n();
  const text = t.documents;
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState<IssuedDocument | null>(null);
  const [previewDone, setPreviewDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  // Follow a running document until it ends.
  useEffect(() => {
    if (!issued || issued.status !== 'PENDING') return undefined;
    let polls = 0;
    const timer = window.setInterval(async () => {
      polls += 1;
      try {
        const next = await getDocument(projectId, issued.id);
        if (!alive.current) return;
        if (next.status !== 'PENDING') {
          window.clearInterval(timer);
          setIssued(next);
        }
      } catch {
        // a missed poll is not an error: the next one asks again
      }
      if (polls >= MAX_POLLS) window.clearInterval(timer);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [issued, projectId]);

  const send = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setIssued(null);
    setPreviewDone(false);
    try {
      if (status === 'DRAFT') {
        await previewEstimatePdf(projectId, estimateId);
        if (alive.current) setPreviewDone(true);
      } else {
        const document = await issueEstimateDocument(projectId, estimateId);
        if (alive.current) setIssued(document);
      }
    } catch (err) {
      if (alive.current) setError(documentErrorText(text.errors, err));
    } finally {
      if (alive.current) setBusy(false);
    }
  }, [busy, estimateId, projectId, status, text.errors]);

  if (status === 'ARCHIVED') return null;
  const isDraft = status === 'DRAFT';
  const running = busy || issued?.status === 'PENDING';

  return (
    <div aria-label="estimate-documents" className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-2">
      <button
        type="button"
        aria-label={isDraft ? 'estimate-preview-pdf' : 'estimate-send-pdf'}
        onClick={() => void send()}
        disabled={running}
        className="w-full min-h-[44px] px-3 text-sm font-semibold text-white bg-sky-700 rounded-xl hover:bg-sky-800 disabled:opacity-60 transition break-words"
      >
        {busy ? text.sending : isDraft ? text.preview_pdf : text.send_pdf}
      </button>
      <p className="text-xs text-slate-600 break-words">{text.chat_hint}</p>

      {issued?.status === 'PENDING' && (
        <p role="status" aria-label="estimate-document-working" className="text-xs text-slate-700 break-words">
          {text.working.replace('{number}', issued.number)}
        </p>
      )}
      {issued?.status === 'SENT' && (
        <p role="status" aria-label="estimate-document-sent" className="text-sm font-medium text-emerald-700 break-words">
          {text.sent_ok.replace('{number}', issued.number)}
        </p>
      )}
      {issued?.status === 'FAILED' && (
        <p role="alert" aria-label="estimate-document-failed" className="text-sm text-red-700 break-words">
          {text.failed.replace('{number}', issued.number)} {documentErrorText(text.errors, issued.error_code ?? undefined)}
        </p>
      )}
      {previewDone && (
        <p role="status" aria-label="estimate-preview-sent" className="text-sm font-medium text-emerald-700 break-words">
          {text.preview_ok}
        </p>
      )}
      {error && (
        <p role="alert" aria-label="estimate-document-error" className="text-sm text-red-700 break-words">
          {error}
        </p>
      )}
    </div>
  );
}
