import { describe, expect, it } from 'vitest';
import pl from '../locales/pl.json';
import en from '../locales/en.json';
import ru from '../locales/ru.json';
import uk from '../locales/uk.json';
import { eventTitle } from './calendarFormat';

describe('eventTitle', () => {
  const events = pl.calendar.event as unknown as Record<string, unknown>;

  it('walks the dictionary by the key of the event', () => {
    expect(eventTitle(events, { title: null, title_key: 'calendar.event.delivery_deadline', kind: 'DELIVERY_DEADLINE' })).toBe('Termin oddania prac');
    expect(eventTitle(events, { title: null, title_key: 'calendar.event.payment_term.advance', kind: 'PAYMENT_TERM' })).toBe('Termin wpłaty zaliczki (§ 6)');
  });

  it('an own reminder has its own words, and an unknown key falls back to the kind', () => {
    expect(eventTitle(events, { title: 'Zadzwonić', title_key: null, kind: 'USER' })).toBe('Zadzwonić');
    expect(eventTitle(events, { title: null, title_key: 'calendar.event.nope', kind: 'BREAK_END' })).toBe('BREAK_END');
  });

  it('puts the name of the invoice into its title (IA-5), in both languages', () => {
    const item = { title: null, title_key: 'calendar.event.invoice_due', kind: 'INVOICE_DUE', params: { what: 'FV 7/2026' } };
    expect(eventTitle(events, item)).toBe('Termin zapłaty faktury: FV 7/2026');
    expect(eventTitle(ru.calendar.event as unknown as Record<string, unknown>, item)).toBe('Срок оплаты фактуры: FV 7/2026');
  });

  it('a word the event does not carry leaves its place empty, never a stray brace; a number is written as it is', () => {
    expect(eventTitle(events, { title: null, title_key: 'calendar.event.invoice_due', kind: 'INVOICE_DUE', params: {} })).toBe('Termin zapłaty faktury: ');
    expect(eventTitle(events, { title: null, title_key: 'calendar.event.invoice_due', kind: 'INVOICE_DUE' })).toBe('Termin zapłaty faktury: ');
    expect(eventTitle(events, { title: null, title_key: 'calendar.event.invoice_due', kind: 'INVOICE_DUE', params: { what: 12 } })).toBe('Termin zapłaty faktury: 12');
  });

  it('a name with braces in it is shown as it is (it is a value, not a template)', () => {
    expect(eventTitle(events, { title: null, title_key: 'calendar.event.invoice_due', kind: 'INVOICE_DUE', params: { what: '{what} {x}' } })).toBe('Termin zapłaty faktury: {what} {x}');
  });

  it('texts without a placeholder are untouched', () => {
    expect(eventTitle(events, { title: null, title_key: 'calendar.event.break_end', kind: 'BREAK_END', params: { what: 'x' } } as never)).toBe(
      'Koniec przerwy technologicznej — można kontynuować prace',
    );
  });
});

describe('the words of the due day of an invoice', () => {
  it('are in both languages with the same placeholder, and the kind has its label in the settings', () => {
    expect(pl.calendar.event.invoice_due).toContain('{what}');
    expect(ru.calendar.event.invoice_due).toContain('{what}');
    expect(pl.calendar.kind.INVOICE_DUE).toBeTruthy();
    expect(ru.calendar.kind.INVOICE_DUE).toBeTruthy();
    expect(Object.keys(pl.calendar.kind).sort()).toEqual(Object.keys(ru.calendar.kind).sort());
  });
});

describe('the words of the due day of a stage of the payment schedule (V2-9b)', () => {
  const item = { title: null, title_key: 'calendar.event.stage_due', kind: 'STAGE_DUE', params: { what: 'Po gładziach' } };

  it('put the title of the stage into the text, in the four languages', () => {
    const of = (dictionary: { calendar: { event: unknown } }) => eventTitle(dictionary.calendar.event as Record<string, unknown>, item);
    expect(of(pl)).toBe('Termin płatności etapu: Po gładziach');
    expect(of(ru)).toBe('Срок оплаты этапа: Po gładziach');
    expect(of(uk)).toBe('Строк оплати етапу: Po gładziach');
    expect(of(en)).toBe('Payment stage due: Po gładziach');
  });

  it('have the same placeholder everywhere, and the kind has its label in the settings', () => {
    for (const dictionary of [pl, ru, uk, en]) {
      expect(dictionary.calendar.event.stage_due).toContain('{what}');
      expect(dictionary.calendar.kind.STAGE_DUE).toBeTruthy();
      expect(dictionary.payments.schedule.due_hint).toBeTruthy();
    }
  });
});
