/** One change made on the phone and not yet accepted by the server (Stage 19C). */
export type OutboxKind =
  | 'note.create' | 'note.update' | 'note.delete'
  | 'room.create' | 'room.update' | 'room.archive' | 'room.restore'
  | 'surface.create' | 'surface.update' | 'surface.archive' | 'surface.restore'
  | 'opening.create' | 'opening.update' | 'opening.archive' | 'opening.restore'
  | 'segment.create' | 'segment.update' | 'segment.archive' | 'segment.restore'
  | 'answers.put'
  | 'inspection.create'
  | 'execution.transition'
  // IA-4: the settlement records of an object (invoices, money from the client, expenses on materials)
  | 'payment.create' | 'payment.update' | 'payment.archive' | 'payment.restore';

export interface OutboxError {
  status: number;
  code?: string;
  message: string;
}

export interface OutboxOp {
  /** Assigned by the store: the order in which the changes were made is the order in which they are sent. */
  seq?: number;
  ownerId: string;
  createdAt: number;
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  body: Record<string, unknown> | null;
  kind: OutboxKind;
  /** The record the change is about (for a create: the id chosen on the phone). */
  entityId: string | null;
  /** A few words for the list of changes ("Salon", "Zadzwonić do…"). */
  label: string;
  /** `pending` waits for the signal; `failed` was refused by the server and needs the owner's attention. */
  status: 'pending' | 'failed';
  attempts: number;
  error?: OutboxError;
}
