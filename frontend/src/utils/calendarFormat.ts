import type { AgendaItem } from '../types/calendar';

const LOCALE_TAGS: Record<string, string> = { pl: 'pl-PL', ru: 'ru-RU' };
const tag = (locale: string) => LOCALE_TAGS[locale] ?? locale;

/** 'YYYY-MM-DD' as a calendar day (local midnight: a day has no zone). */
export function parseDay(day: string): Date {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(year, month - 1, date);
}

/** "pon., 12 paź" -- the weekday and the day, short enough for a phone. */
export function formatDay(day: string, locale: string): string {
  return parseDay(day).toLocaleDateString(tag(locale), { weekday: 'short', day: 'numeric', month: 'short' });
}

export function formatShortDate(day: string, locale: string): string {
  return parseDay(day).toLocaleDateString(tag(locale), { day: 'numeric', month: 'numeric', year: 'numeric' });
}

/** The time of an instant in the owner's zone ("14:30"). */
export function formatTime(iso: string, locale: string, timeZone: string): string {
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  const date = new Date(hasOffset ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString(tag(locale), { hour: '2-digit', minute: '2-digit', timeZone });
}

/** "12.10, 14:30" -- a day and a time of an instant, in the owner's zone. */
export function formatDayTime(iso: string, locale: string, timeZone?: string): string {
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  const date = new Date(hasOffset ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(tag(locale), { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit', timeZone });
}

/** Today's date in the browser as 'YYYY-MM-DD'. */
export function todayIso(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** The words of an event: its key `calendar.event.<kind>[.<part>]` walks the dictionary; an own reminder has its own words. */
export function eventTitle(events: Record<string, unknown>, item: Pick<AgendaItem, 'title' | 'title_key' | 'kind'>): string {
  if (item.title) return item.title;
  const path = (item.title_key ?? '').replace(/^calendar\.event\./, '').split('.');
  let node: unknown = events;
  for (const part of path) {
    node = node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined;
  }
  return typeof node === 'string' ? node : item.kind;
}
