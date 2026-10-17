/** The settlement records of an object (invoices and advances); mirrors backend `schemas/payment.py`. Money arrives as strings with two places. */
export type PaymentKind = 'INVOICE' | 'ADVANCE' | 'PAYMENT' | 'EXPENSE';
export type PaymentDocumentKind = 'RECEIPT' | 'INVOICE';
export type InvoiceState = 'PAID' | 'PARTIAL' | 'OVERDUE' | 'OPEN';

export interface Payment {
  id: string;
  project_id: string;
  kind: PaymentKind;
  title: string;
  number: string | null;
  amount_gross: string;
  amount_net: string | null;
  vat_rate: string | null;
  occurred_on: string;
  due_on: string | null;
  settles_id: string | null;
  counterparty: string | null;
  document_kind: PaymentDocumentKind | null;
  note: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  /** An invoice only: what the payments tied to it settled, what is left, and where it stands. */
  settled: string | null;
  remaining: string | null;
  state: InvoiceState | null;
  /** Made on the phone and not yet accepted by the server (Stage 19E): the screens mark it, and what the server derives is empty. */
  _pending?: boolean;
}

export interface PaymentSummary {
  invoiced: string;
  received: string;
  expenses: string;
  invoiced_unpaid: string;
  to_receive: string | null;
  result: string;
}

export interface PaymentList {
  items: Payment[];
  total: number;
  summary: PaymentSummary;
  agreed_amount: string | null;
}

export interface AgreedSuggestion {
  amount: string;
  estimate_id: string;
  estimate_version: number;
  status: string;
}

export interface Finance {
  agreed_amount: string | null;
  currency: string;
  suggestion: AgreedSuggestion | null;
}

/** What the form sends; an empty optional field is `null` (it clears the value on a change). */
export interface PaymentFields {
  title: string;
  amount_gross: string;
  occurred_on: string;
  number: string | null;
  amount_net: string | null;
  vat_rate: string | null;
  due_on: string | null;
  settles_id: string | null;
  counterparty: string | null;
  document_kind: PaymentDocumentKind | null;
  note: string | null;
}

/** Same limits as the backend schema. */
export const MAX_TITLE_LENGTH = 500;
export const MAX_NUMBER_LENGTH = 64;
export const MAX_COUNTERPARTY_LENGTH = 255;
export const MAX_NOTE_LENGTH = 4000;
