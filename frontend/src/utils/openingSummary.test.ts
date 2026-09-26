import { describe, expect, it } from 'vitest';
import { OpeningType } from '../types/opening';
import { formatOpeningDimension, summarizeOpenings } from './openingSummary';

function opening(type: OpeningType['opening_type'], width: string, height: string, quantity = 1, archived = false): OpeningType {
  return {
    id: `${type}-${width}-${height}-${quantity}-${archived}-${Math.random()}`, surface_id: 's', opening_type: type, name: null,
    width, height, quantity, single_area: null, total_area: null, description: null, reveal_enabled: false,
    reveal_depth: null, reveal_left: false, reveal_right: false, reveal_top: false, reveal_bottom: false,
    reveal_single_length: null, reveal_single_area: null, reveal_total_length: null, reveal_total_area: null,
    is_archived: archived, created_at: '', updated_at: '',
  };
}

describe('summarizeOpenings (13E.5B)', () => {
  it('groups by type + dimensions, sums quantity, excludes archived, orders DOOR/WINDOW/OTHER then size', () => {
    const rows = summarizeOpenings([
      opening('WINDOW', '2.100', '1.400'),
      opening('OTHER', '0.300', '0.300'),
      opening('DOOR', '0.900', '2.070', 2),
      opening('WINDOW', '0.600', '1.400'),
      opening('WINDOW', '9.990', '9.990', 1, true),
    ]);
    expect(rows).toEqual([
      { openingType: 'DOOR', width: '0.900', height: '2.070', count: 2 },
      { openingType: 'WINDOW', width: '0.600', height: '1.400', count: 1 },
      { openingType: 'WINDOW', width: '2.100', height: '1.400', count: 1 },
      { openingType: 'OTHER', width: '0.300', height: '0.300', count: 1 },
    ]);
  });

  it('aggregates identical openings across rows and normalizes decimal representations', () => {
    const rows = summarizeOpenings([opening('DOOR', '0.9', '2.07'), opening('DOOR', '0.900', '2.070', 3)]);
    expect(rows).toEqual([{ openingType: 'DOOR', width: '0.900', height: '2.070', count: 4 }]);
  });

  it('is empty without active openings', () => {
    expect(summarizeOpenings([])).toEqual([]);
    expect(summarizeOpenings(undefined)).toEqual([]);
    expect(summarizeOpenings([opening('WINDOW', '1', '1', 1, true)])).toEqual([]);
  });

  it('formats dimensions with a decimal comma', () => {
    expect(formatOpeningDimension('0.900')).toBe('0,90');
    expect(formatOpeningDimension('2.070')).toBe('2,07');
  });
});
