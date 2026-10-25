import { useEffect, useRef, useState } from 'react';
import {
  issueMeasurements,
  issuePaymentSchedule,
  issueProductionPlan,
  issueSettlement,
  issueTechCard,
  previewMeasurementsPdf,
  previewPaymentSchedulePdf,
  previewProductionPlanPdf,
  previewSettlementPdf,
  previewTechCardPdf,
} from '../api/documents';
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

type SectionKind = 'tech-card' | 'production-plan' | 'settlement' | 'measurements' | 'payment-schedule';

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
  const words =
    sectionKind === 'tech-card'
      ? { title: text.tech_card, hint: text.tech_card_hint, preview: text.tech_card_preview, send: text.tech_card_send, previewOk: text.tech_card_preview_ok }
      : sectionKind === 'settlement'
        ? { title: text.settlement, hint: text.settlement_hint, preview: text.settlement_preview, send: text.settlement_send, previewOk: text.settlement_preview_ok }
        : sectionKind === 'payment-schedule'
          ? { title: text.payment_schedule_title, hint: text.payment_schedule_hint, preview: text.payment_schedule_preview, send: text.payment_schedule_send, previewOk: text.payment_schedule_preview_ok }
          : sectionKind === 'measurements'
          ? { title: text.measurements_title, hint: text.measurements_hint, preview: text.measurements_preview, send: text.measurements_send, previewOk: text.measurements_preview_ok }
          : { title: text.production_plan, hint: text.production_plan_hint, preview: text.production_plan_preview, send: text.production_plan_send, previewOk: text.production_plan_preview_ok };
  const [withPhotos, setWithPhotos] = useState(false); // measurements only: the photos of the surfaces go under their sizes
  // looked up only when a button is tapped (a screen that mocks part of the api never reaches the others)
  const previewers = {
    'tech-card': () => previewTechCardPdf(projectId),
    settlement: () => previewSettlementPdf(projectId),
    measurements: () => previewMeasurementsPdf(projectId, withPhotos),
    'payment-schedule': () => previewPaymentSchedulePdf(projectId),
    'production-plan': () => previewProductionPlanPdf(projectId),
  };
  const issuers = {
    'tech-card': () => issueTechCard(projectId),
    settlement: () => issueSettlement(projectId),
    measurements: () => issueMeasurements(projectId, withPhotos),
    'payment-schedule': () => issuePaymentSchedule(projectId),
    'production-plan': () => issueProductionPlan(projectId),
  };
  const preview = previewers[sectionKind];
  const issue = issuers[sectionKind];
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
        await preview();
        if (alive.current) setNote(words.previewOk);
      } else {
        await issue();
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
      {sectionKind === 'measurements' && (
        <label className="flex items-start gap-3 min-h-11 py-2 text-sm text-slate-900 cursor-pointer">
          <input
            type="checkbox"
            checked={withPhotos}
            onChange={(event) => setWithPhotos(event.target.checked)}
            disabled={busy !== null}
            className="mt-0.5 h-6 w-6 shrink-0 accent-sky-700"
          />
          <span className="min-w-0 break-words">
            <span className="font-semibold">{text.measurements_with_photos}</span>
            <span className="block text-xs text-slate-600">{text.measurements_with_photos_hint}</span>
          </span>
        </label>
      )}
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

/** V2-8c — the measurements of the object (Obmiar obiektu): every size of every room, the same numbers as the screens. */
export function MeasurementsSection(props: DocumentSectionProps) {
  return <DocumentSection {...props} kind="measurements" />;
}

/** V2-9a — the payment schedule of the object (Harmonogram płatności): the stages in which the client pays, with the day and the state of each. */
export function PaymentScheduleSection(props: DocumentSectionProps) {
  return <DocumentSection {...props} kind="payment-schedule" />;
}

/** Stage 16D.2 — the production plan: the order of the works, the technological breaks, the works of other contractors. */
export function ProductionPlanSection(props: DocumentSectionProps) {
  return <DocumentSection {...props} kind="production-plan" />;
}

/** IA-6a — the statement of settlements "Rozliczenie" for the client: what was invoiced and what was paid; never the owner's expenses. */
export function SettlementSection(props: DocumentSectionProps) {
  return <DocumentSection {...props} kind="settlement" />;
}
