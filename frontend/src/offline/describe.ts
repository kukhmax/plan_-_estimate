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

/**
 * The words of a waiting change on the sync screen. The outbox keeps the label as it was made ("IN_PROGRESS", "FLOOR 300 × 400", "CONCRETE"),
 * so the codes (work status, plane, substrate, opening type) are turned into the user's language here, at display time — also for the
 * changes already waiting on a phone.
 */
export interface LabelWords {
  status: Record<string, string>;
  inspections: Record<string, string>;
  openings: Record<string, string>;
  planes: { floor: string; ceiling: string };
}

export function describeLabel(label: string, words: LabelWords): string {
  const codes: Record<string, string | undefined> = {
    ...Object.fromEntries(Object.entries(words.status)),
    FLOOR: words.planes.floor,
    CEILING: words.planes.ceiling,
    DOOR: words.openings.door,
    WINDOW: words.openings.window,
    OTHER: words.openings.other,
  };
  return label
    .split(' ')
    .map((token) => {
      if (!/^[A-Z][A-Z_]+$/.test(token)) return token;
      return codes[token] ?? words.inspections[`substrate_${token.toLowerCase()}`] ?? token;
    })
    .join(' ');
}
