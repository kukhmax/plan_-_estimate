import { describe, expect, it } from 'vitest';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { ALL_KINDS, describeLabel, refusalReason } from './describe';
import { previewArea } from './preview';

describe('why the server refused a change (Stage 19E)', () => {
  it.each([
    [{ status: 409, message: 'x' }, 'reason_conflict'],
    [{ status: 409, code: 'CLIENT_ID_CONFLICT', message: 'x' }, 'reason_conflict'],
    [{ status: 409, code: 'WORK_EXECUTION_CONFLICT', message: 'x' }, 'reason_status_changed'],
    [{ status: 404, message: 'x' }, 'reason_missing'],
    [{ status: 422, message: 'x' }, 'reason_invalid'],
    [{ status: 400, message: 'x' }, 'reason_invalid'],
    [{ status: 503, message: 'x' }, 'reason_server'],
    [{ status: 429, message: 'x' }, 'reason_server'],
    [{ status: 403, message: 'x' }, 'reason_other'],
    [undefined, 'reason_other'],
  ])('%j → %s', (error, reason) => {
    expect(refusalReason(error as never)).toBe(reason);
  });

  it('every kind of change has a name in both languages, and every reason a text', () => {
    for (const dict of [pl.offline, ru.offline] as Array<Record<string, unknown>>) {
      const kinds = dict.kinds as Record<string, string>;
      for (const kind of ALL_KINDS) expect(kinds[kind], kind).toBeTruthy();
      expect(Object.keys(kinds).sort()).toEqual([...ALL_KINDS].sort());
      for (const reason of ['reason_conflict', 'reason_missing', 'reason_invalid', 'reason_server', 'reason_other', 'reason_status_changed']) {
        expect(dict[reason], reason).toBeTruthy();
      }
    }
  });
});

describe('the preview of an area the phone only knows (Q5 (b))', () => {
  it('is the typed width times height, to two decimals', () => {
    expect(previewArea('3.73', '2.68')).toBe('10,00');
    expect(previewArea(3.73, 2.68)).toBe('10,00');
    expect(previewArea('4', 2.5)).toBe('10,00');
  });
  it.each([[null, 2], [2, undefined], ['', 3], ['abc', 3], [0, 3], [-1, 3], [{}, 3]])('is nothing for %j × %j', (w, h) => {
    expect(previewArea(w, h)).toBeNull();
  });
});

describe('the words of a waiting change (codes are translated at display time)', () => {
  const words = (dict: typeof pl) => ({
    status: dict.execution.status as Record<string, string>,
    inspections: dict.inspections as unknown as Record<string, string>,
    openings: dict.openings as unknown as Record<string, string>,
    planes: { floor: dict.area_segments.floor, ceiling: dict.area_segments.ceiling },
  });
  it('translates work statuses, substrates, planes and opening types in both languages', () => {
    expect(describeLabel('IN_PROGRESS', words(pl))).toBe(pl.execution.status.IN_PROGRESS);
    expect(describeLabel('COMPLETED', words(ru as typeof pl))).toBe((ru as typeof pl).execution.status.COMPLETED);
    expect(describeLabel('CONCRETE', words(pl))).toBe(pl.inspections.substrate_concrete);
    expect(describeLabel('FLOOR CONCRETE', words(pl))).toBe(`${pl.area_segments.floor} ${pl.inspections.substrate_concrete}`);
    expect(describeLabel('FLOOR 300 × 400', words(pl))).toBe(`${pl.area_segments.floor} 300 × 400`);
    expect(describeLabel('DOOR 90 × 200', words(pl))).toBe(`${pl.openings.door} 90 × 200`);
  });
  it('leaves the user\'s own words and unknown codes alone', () => {
    expect(describeLabel('Ściana 3', words(pl))).toBe('Ściana 3');
    expect(describeLabel('UNKNOWN_CODE', words(pl))).toBe('UNKNOWN_CODE');
    expect(describeLabel('', words(pl))).toBe('');
  });
});
