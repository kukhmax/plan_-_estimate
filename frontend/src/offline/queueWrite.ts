import { addOp, listOps } from './outbox';
import { askForSending } from './outboxState';
import { currentOfflineOwner, loadReadsByPrefix } from './readCache';
import { cachePrefix, labelOf, optimisticResult, type WriteMatch } from './writeRules';

/**
 * Keeps a write on the phone (Stage 19C) and gives the screen the answer it expects. `null` when it cannot be kept (no owner known, no
 * IndexedDB): the caller then fails exactly as before.
 */
export async function queueWrite(
  match: WriteMatch,
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body: Record<string, unknown> | null,
): Promise<{ result: unknown } | null> {
  const ownerId = currentOfflineOwner();
  if (!ownerId) return null;
  const idKeys = { note: 'note', room: 'room', surface: 'surface', opening: 'opening', segment: 'segment', answers: 'inspection', inspection: 'inspection', execution: 'occurrence', payment: 'payment' } as const;
  const entityId = match.action === 'create' ? ((body?.id as string | undefined) ?? null) : (match.ids[idKeys[match.entity]] ?? null);
  const op = await addOp({
    ownerId,
    createdAt: Date.now(),
    method,
    path,
    body,
    kind: match.kind,
    entityId,
    label: labelOf(match, body),
  });
  if (!op) return null;
  const [ops, saved] = await Promise.all([listOps(), loadReadsByPrefix(cachePrefix(match))]);
  const result = optimisticResult(op, saved, ops);
  askForSending();
  return { result };
}
