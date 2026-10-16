import type { OutboxError, OutboxKind } from './opTypes';

/** Why the server refused a change, in the words of the sync screen (the key of `t.offline`). Never the server's own English text. */
export type RefusalReason = 'reason_conflict' | 'reason_missing' | 'reason_invalid' | 'reason_server' | 'reason_other' | 'reason_status_changed';

export function refusalReason(error: OutboxError | undefined): RefusalReason {
  if (!error) return 'reason_other';
  if (error.code === 'WORK_EXECUTION_CONFLICT') return 'reason_status_changed';
  if (error.code === 'CLIENT_ID_CONFLICT' || error.status === 409) return 'reason_conflict';
  if (error.status === 404) return 'reason_missing';
  if (error.status === 400 || error.status === 422) return 'reason_invalid';
  if (error.status >= 500 || error.status === 429 || error.status === 408) return 'reason_server';
  return 'reason_other';
}

export const ALL_KINDS: readonly OutboxKind[] = [
  'note.create', 'note.update', 'note.delete',
  'room.create', 'room.update', 'room.archive', 'room.restore',
  'surface.create', 'surface.update', 'surface.archive', 'surface.restore',
  'opening.create', 'opening.update', 'opening.archive', 'opening.restore',
  'segment.create', 'segment.update', 'segment.archive', 'segment.restore',
  'answers.put', 'inspection.create', 'execution.transition',
];
