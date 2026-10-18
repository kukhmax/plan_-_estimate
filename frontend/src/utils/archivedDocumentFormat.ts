import type { ArchivedDocumentKind } from '../types/archivedDocument';

/** The names of the kinds are `archive.document_kind_*` of the locales; `text` is that section. */
export interface ArchivedDocumentKindTexts {
  document_kind_contract: string;
  document_kind_handover: string;
  document_kind_concealed: string;
  document_kind_acceptance: string;
  document_kind_decision: string;
  document_kind_downtime: string;
}

export function archivedDocumentKindLabel(text: ArchivedDocumentKindTexts, kind: ArchivedDocumentKind): string {
  switch (kind) {
    case 'CONTRACT':
      return text.document_kind_contract;
    case 'HANDOVER':
      return text.document_kind_handover;
    case 'CONCEALED':
      return text.document_kind_concealed;
    case 'ACCEPTANCE':
      return text.document_kind_acceptance;
    case 'DECISION':
      return text.document_kind_decision;
    default:
      return text.document_kind_downtime;
  }
}
