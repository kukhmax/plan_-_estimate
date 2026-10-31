/** V2-8 — the link for the client: the owner's side and the open page of the client (mirrors backend/app/schemas/client_link.py and client_portal.py). */
import type { Locale } from '../utils/locale';

export interface ClientLinkInfo {
  id: string;
  language: Locale;
  created_at: string;
  expires_at: string;
  last_viewed_at: string | null;
  view_count: number;
  expired: boolean;
}

export interface ClientLinkStatus {
  link: ClientLinkInfo | null;
}

export interface ClientLinkIssued {
  link: ClientLinkInfo;
  token: string;
}

export type ProposalStatus = 'OPEN' | 'ACCEPTED' | 'DECLINED' | 'WITHDRAWN';

export interface ClientProposal {
  id: string;
  sequence: number;
  title: string;
  description: string | null;
  amount: string;
  currency: string;
  extra_days: number | null;
  status: ProposalStatus;
  created_at: string;
  decided_at: string | null;
}

export interface ClientProposalList {
  items: ClientProposal[];
  max_proposals: number;
}

export interface ClientProposalInput {
  title: string;
  description: string | null;
  amount: string;
  extra_days: number | null;
}

export type ConsentKind = 'ESTIMATE_ACCEPTED' | 'ESTIMATE_DECLINED' | 'PROPOSAL_ACCEPTED' | 'PROPOSAL_DECLINED';

export interface ClientConsent {
  id: string;
  kind: ConsentKind;
  estimate_id: string | null;
  estimate_version: number | null;
  proposal_id: string | null;
  subject_hash: string;
  amount: string;
  currency: string;
  statement: string;
  statement_lang: string;
  signer_name: string;
  comment: string | null;
  created_at: string;
}

export interface ClientJournal {
  items: ClientConsent[];
}

// --- the open page -----------------------------------------------------------------------------------------------------------

export interface PortalContractor {
  name: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
}

export interface PortalProject {
  name: string;
  address: string;
  city: string;
  postal_code: string;
  /** UX walk: the name of the private client of the object, offered in the approval form. */
  client_name?: string | null;
}

export interface PortalLine {
  position: number;
  room_name: string | null;
  surface_name: string | null;
  description: string;
  unit: string;
  quantity: string;
  unit_price: string | null;
  amount: string | null;
  /** LABOR / MATERIAL / LABOR_AND_MATERIAL (UX walk: the materials get their own group). */
  scope?: string | null;
}

export interface PortalStatement {
  pl: string;
  text: string;
}

export interface PortalConsent {
  kind: ConsentKind;
  signer_name: string;
  comment: string | null;
  created_at: string;
}

export interface PortalEstimate {
  id: string;
  version: number;
  status: 'FINAL' | 'ACCEPTED';
  name: string | null;
  currency: string;
  total: string | null;
  vat_mode: string | null;
  vat_rate_percent: number | null;
  vat_included?: boolean;
  net_total?: string | null;
  vat_amount: string | null;
  gross_total: string | null;
  hash: string;
  lines: PortalLine[];
  consent: PortalConsent | null;
  accept_statement: PortalStatement | null;
  decline_statement: PortalStatement | null;
}

export interface PortalProposal {
  id: string;
  sequence: number;
  title: string;
  description: string | null;
  amount: string;
  currency: string;
  extra_days: number | null;
  status: Exclude<ProposalStatus, 'WITHDRAWN'>;
  hash: string;
  created_at: string;
  consent: PortalConsent | null;
  accept_statement: PortalStatement | null;
  decline_statement: PortalStatement | null;
}

export interface PortalPage {
  link: { expires_at: string; language: Locale };
  lang: Locale;
  contractor: PortalContractor;
  project: PortalProject;
  estimate: PortalEstimate | null;
  proposals: PortalProposal[];
}

export interface PortalEstimateDecision {
  estimate_id: string;
  version: number;
  hash: string;
  decision: 'ACCEPT' | 'DECLINE';
  signer_name: string;
  agree: boolean;
  comment?: string | null;
}

export interface PortalDecideInput {
  decision: 'ACCEPT' | 'DECLINE';
  hash: string;
  signer_name: string;
  agree: boolean;
  comment?: string | null;
}

/** The address the client opens; the secret stays after the `#`, which a browser never sends to a server. */
export function clientLinkUrl(origin: string, token: string): string {
  return `${origin.replace(/\/$/, '')}/c#${token}`;
}

export interface PortalWhyPhoto {
  thumb_url: string;
  url: string;
  width: number;
  height: number;
}

export interface PortalWhyReason {
  surface_name: string | null;
  work_name_key: string | null;
  work_name: string | null;
  reason_key: string;
  inspected_on: string | null;
  photos: PortalWhyPhoto[];
}

export interface PortalWhyRoom {
  room_name: string;
  quality_target: string | null;
  reasons: PortalWhyReason[];
}

/** Owner 2026-10-31: the standard of each room and the reasons from the inspections ("Dlaczego te prace?"). */
export interface PortalWhy {
  rooms: PortalWhyRoom[];
}
