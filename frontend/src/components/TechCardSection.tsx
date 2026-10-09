import { useEffect, useRef, useState } from 'react';
import { issueProductionPlan, issueTechCard, previewProductionPlanPdf, previewTechCardPdf } from '../api/documents';
import { ApiError } from '../api/http';
import { useI18n } from '../hooks/useI18n';
import type { TechCardMissingItem } from '../types/document';
import { documentErrorText } from '../utils/documentErrors';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';

interface DocumentSectionProps {
  projectId: string;
  /** The journal changed (a numbered document was started): the card reloads its list and follows it. */
  onIssued: () => void;
}

type SectionKind = 'tech-card' | 'production-plan';

/** The surfaces the server named in `TECH_CARD_INCOMPLETE`, if that is what the error was. */
function missingItems(error: unknown): TechCardMissingItem[] {
  if (!(error instanceof ApiError) || error.code !== 'TECH_CARD_INCOMPLETE') return [];
  const detail = error.detail as { details?: { items?: TechCardMissingItem[] } } | null;
  return detail?.details?.items ?? [];
}

/**
 * Stages 16C / 16D.2 — a working document of an object (the technological card, the production plan). Two actions, both ending in the owner's chat with the bot:
 * the **working version** (watermark, no number, empty lines to write in for whatever is not filled in yet — to print and talk
 * through with the customer) and the **numbered card** (refused with the list of what is missing until every surface with
 * works has its agreed standard and a finished inspection).
 */
function DocumentSection({ projectId, onIssued, kind: sectionKind }: DocumentSectionProps & { kind: SectionKind }) {
  const { t } = useI18n();
  const text = t.documents;
  const isCard = sectionKind === 'tech-card';
  const words = isCard
    ? { title: text.tech_card, hint: text.tech_card_hint, preview: text.tech_card_preview, send: text.tech_card_send, previewOk: text.tech_card_preview_ok }
    : { title: text.production_plan, hint: text.production_plan_hint, preview: text.production_plan_preview, send: text.production_plan_send, previewOk: text.production_plan_preview_ok };
  const [busy, setBusy] = useState<'preview' | 'issue' | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState<TechCardMissingItem[]>([]);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const run = async (kind: 'preview' | 'issue') => {
    if (busy) return;
    setBusy(kind);
    setNote(null);
    setError(null);
    setMissing([]);
    try {
      if (kind === 'preview') {
        await (isCard ? previewTechCardPdf(projectId) : previewProductionPlanPdf(projectId));
        if (alive.current) setNote(words.previewOk);
      } else {
        await (isCard ? issueTechCard(projectId) : issueProductionPlan(projectId));
        if (alive.current) onIssued();
      }
    } catch (err) {
      if (!alive.current) return;
      setError(documentErrorText(text.errors, err));
      setMissing(missingItems(err));
    } finally {
      if (alive.current) setBusy(null);
    }
  };

  const surfaceLabels = { wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling };
  const missingText = (code: string): string => text.tech_card_missing[code as keyof typeof text.tech_card_missing] ?? code;

  return (
    <section aria-label={`${sectionKind}-card`} className="space-y-2">
      <h4 className="text-sm font-semibold text-slate-900 break-words">{words.title}</h4>
      <p className="text-sm text-slate-700 break-words">{words.hint}</p>
      <button
        type="button"
        aria-label={`preview-${sectionKind}`}
        onClick={() => void run('preview')}
        disabled={busy !== null}
        className="w-full min-h-11 px-3 text-sm font-semibold text-slate-900 bg-slate-100 border border-slate-300 rounded-xl hover:bg-slate-200 disabled:opacity-60 transition break-words"
      >
        {busy === 'preview' ? text.sending : words.preview}
      </button>
      <button
        type="button"
        aria-label={`send-${sectionKind}`}
        onClick={() => void run('issue')}
        disabled={busy !== null}
        className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-sky-700 rounded-xl hover:bg-sky-800 disabled:opacity-60 transition break-words"
      >
        {busy === 'issue' ? text.sending : words.send}
      </button>
      <p className="text-xs text-slate-500 break-words">{text.chat_hint}</p>
      {note && <p role="status" aria-label={`${sectionKind}-note`} className="text-sm text-emerald-800 break-words">{note}</p>}
      {error && <p role="alert" aria-label={`${sectionKind}-error`} className="text-sm text-red-700 break-words">{error}</p>}
      {missing.length > 0 && (
        <div aria-label={`${sectionKind}-missing`} className="space-y-1">
          <p className="text-xs font-semibold text-slate-700 break-words">{text.tech_card_missing_title}</p>
          <ul className="space-y-1">
            {missing.map((item) => (
              <li key={`${item.room}-${item.surface}`} className="text-xs text-slate-700 break-words bg-red-50 border border-red-200 rounded-xl px-3 py-2">
                <span className="font-semibold">
                  {item.room} › {getSurfaceDisplayName({ name: item.surface, surface_type: item.surface_type }, surfaceLabels)}
                </span>
                {': '}
                {item.missing.map(missingText).join('; ')}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** Stage 16C — the technological card: numbered form refused with the list of what each surface lacks, working form with empty lines. */
export function TechCardSection(props: DocumentSectionProps) {
  return <DocumentSection {...props} kind="tech-card" />;
}

/** Stage 16D.2 — the production plan: the order of the works, the technological breaks, the works of other contractors. */
export function ProductionPlanSection(props: DocumentSectionProps) {
  return <DocumentSection {...props} kind="production-plan" />;
}
