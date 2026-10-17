import type { Finance, Payment, PaymentFields, PaymentKind, PaymentList } from '../types/payment';
import { apiRequest } from './http';

const basePath = (projectId: string) => `/api/projects/${projectId}/payments`;

/** Every active record of the object with the summary; the screen sorts them into its tabs. */
export function fetchPayments(projectId: string, includeArchived = false): Promise<PaymentList> {
  return apiRequest(`${basePath(projectId)}${includeArchived ? '?include_archived=true' : ''}`);
}

/** The id is made on the phone: sending the same record again answers with the one already saved. */
export function createPayment(projectId: string, id: string, kind: PaymentKind, fields: PaymentFields): Promise<Payment> {
  return apiRequest(basePath(projectId), { method: 'POST', body: JSON.stringify({ id, kind, ...fields }) });
}

/** The kind never changes; only what is sent changes. */
export function updatePayment(projectId: string, paymentId: string, fields: Partial<PaymentFields>): Promise<Payment> {
  return apiRequest(`${basePath(projectId)}/${paymentId}`, { method: 'PATCH', body: JSON.stringify(fields) });
}

/** A record is never erased: it is archived, and restored from the same list. */
export function archivePayment(projectId: string, paymentId: string): Promise<Payment> {
  return apiRequest(`${basePath(projectId)}/${paymentId}/archive`, { method: 'POST' });
}

export function restorePayment(projectId: string, paymentId: string): Promise<Payment> {
  return apiRequest(`${basePath(projectId)}/${paymentId}/restore`, { method: 'POST' });
}

export function fetchFinance(projectId: string): Promise<Finance> {
  return apiRequest(`/api/projects/${projectId}/finance`);
}

/** `null` clears the agreed amount. */
export function saveAgreedAmount(projectId: string, agreedAmount: string | null): Promise<Finance> {
  return apiRequest(`/api/projects/${projectId}/finance`, { method: 'PUT', body: JSON.stringify({ agreed_amount: agreedAmount }) });
}
