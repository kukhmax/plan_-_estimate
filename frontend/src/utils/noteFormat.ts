import { localeTag } from './locale';

/** "15.10.2026, 14:30" -- the day and the time a note was written, in the time of the phone; the raw text when the instant is unreadable. */
export function formatNoteTime(iso: string, locale: string): string {
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);

  const date = new Date(hasOffset ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(localeTag(locale), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
