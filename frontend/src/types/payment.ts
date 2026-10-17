/** The settlement records of an object (invoices and advances); mirrors backend `schemas/payment.py`. Money arrives as strings with two places. */
export type PaymentKind = 'INVOICE' | 'ADVANCE' | 'PAYMENT' | 'EXPENSE';
export type PaymentDocumentKind = 'RECEIPT' | 'INVOICE';
/** What an expense was spent on (IA-6b); the words of the backend `ExpenseCategory`. */
export type PaymentCategory = 'MATERIALS' | 'TOOLS' | 'TRANSPORT' | 'SERVICES' | 'OTHER';
export const PAYMENT_CATEGORIES: readonly PaymentCategory[] = ['MATERIALS', 'TOOLS', 'TRANSPORT', 'SERVICES', 'OTHER'];
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
  /** An expense only; an expense made before the categories existed has none (a list kept on the phone from before may lack the field). */
  category?: PaymentCategory | null;
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
  /** The parts of `expenses`, only the categories that have any (null: the ones with no category); a list kept from before may lack it. */
  expenses_by_category?: { category: PaymentCategory | null; total: string }[];
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
  category: PaymentCategory | null;
  note: string | null;
}

/** One archived record in the archive of all objects (IA-7); `photos` are its receipt / invoice photos, which go with it. */
export interface ArchivedPaymentItem {
  id: string;
  project_id: string;
  project_name: string;
  kind: PaymentKind;
  title: string;
  number: string | null;
  amount_gross: string;
  occurred_on: string;
  counterparty: string | null;
  category: PaymentCategory | null;
  photos: number;
}

export interface ArchivedPayments {
  items: ArchivedPaymentItem[];
  /** The list holds the first 200; the total is whole. */
  total: number;
}

/** What deleting an archived record for good would remove, counted by the server (IA-7). */
export interface PaymentPurgePreview {
  target_id: string;
  kind: PaymentKind;
  title: string;
  archived: boolean;
  can_purge: boolean;
  /** Of an invoice: the payments that settled it stay (the money is theirs) and lose the link. */
  tied_payments: number;
  photos: number;
  /** File sets (original, display, thumbnail) that leave the storage: those no other photo still uses. */
  photo_files: number;
  bytes: number;
  annotations: number;
  may_be_in_backups: boolean;
}

export interface PaymentPurgeResult {
  purged: boolean;
  photo_files: number;
  /** File sets still to be removed from the storage: a retry finishes them. */
  storage_pending: number;
}

/** Same limits as the backend schema. */
export const MAX_TITLE_LENGTH = 500;
export const MAX_NUMBER_LENGTH = 64;
export const MAX_COUNTERPARTY_LENGTH = 255;
export const MAX_NOTE_LENGTH = 4000;
