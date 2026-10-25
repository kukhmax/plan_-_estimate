import { localeTag } from './locale';
import type { DocumentKind } from '../types/document';

/** The date and time of a journal row in Polish local time, in the language of the screen. */
export function formatIssued(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(localeTag(locale), {
    timeZone: 'Europe/Warsaw',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatSize(bytes: number): string {
  return bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

/** The names of the kinds of documents are in `documents.kind_*` of the locales; `text` is that section. */
export interface DocumentKindTexts {
  kind_estimate: string;
  kind_photo_report: string;
  kind_tech_card: string;
  kind_production_plan: string;
  kind_contract: string;
  kind_handover: string;
  kind_concealed: string;
  kind_final: string;
  kind_decision: string;
  kind_downtime_notice: string;
  kind_downtime_protocol: string;
  kind_settlement: string;
  kind_measurements: string;
  kind_payment_schedule: string;
}

export function documentKindLabel(text: DocumentKindTexts, kind: DocumentKind): string {
  const labels: Record<DocumentKind, string> = {
    ESTIMATE: text.kind_estimate,
    PHOTO_REPORT: text.kind_photo_report,
    TECH_CARD: text.kind_tech_card,
    PRODUCTION_PLAN: text.kind_production_plan,
    CONTRACT: text.kind_contract,
    HANDOVER_PROTOCOL: text.kind_handover,
    CONCEALED_WORKS_PROTOCOL: text.kind_concealed,
    FINAL_PROTOCOL: text.kind_final,
    DECISION_PROTOCOL: text.kind_decision,
    DOWNTIME_NOTICE: text.kind_downtime_notice,
    DOWNTIME_PROTOCOL: text.kind_downtime_protocol,
    SETTLEMENT: text.kind_settlement,
    MEASUREMENTS: text.kind_measurements,
    PAYMENT_SCHEDULE: text.kind_payment_schedule,
  };
  return labels[kind];
}
