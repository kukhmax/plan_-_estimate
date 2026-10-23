import { describe, expect, it } from 'vitest';
import { commaDecimal, dotDecimal, formatDecimalMoney, formatMetric, formatQuantity, signedMoneyDifference } from './format';

describe('formatMetric — two-decimal metric policy (Stage 7 final)', () => {
  it('renders every construction metric to exactly two decimals', () => {
    expect(formatMetric('5.000')).toBe('5,00'); // room length
    expect(formatMetric('4.900')).toBe('4,90'); // room width
    expect(formatMetric('2.700')).toBe('2,70'); // room / wall height
    expect(formatMetric('1.800')).toBe('1,80'); // opening single area
    expect(formatMetric('30.090')).toBe('30,09'); // floor area
    expect(formatMetric('12.210')).toBe('12,21'); // area segment total
    expect(formatMetric('3.000')).toBe('3,00'); // risk numeric snapshot (mm)
  });

  it('rounds three-decimal backend values to two decimals for display only', () => {
    expect(formatMetric('13.515')).toBe('13,52'); // wall 13.515 m²
    expect(formatMetric('0.005')).toBe('0,01');
    expect(formatMetric('0.004')).toBe('0,00');
  });

  it('formats numeric inputs consistently', () => {
    expect(formatMetric(5)).toBe('5,00');
    expect(formatMetric(4.9)).toBe('4,90');
    expect(formatMetric(48.6)).toBe('48,60');
    expect(formatMetric(0)).toBe('0,00');
  });

  it('renders empty and non-numeric values as an em dash', () => {
    expect(formatMetric(null)).toBe('—');
    expect(formatMetric(undefined)).toBe('—');
    expect(formatMetric('')).toBe('—');
    expect(formatMetric('abc')).toBe('—');
  });
});

describe('formatDecimalMoney — string-only decimal display (Stage 10G.1)', () => {
  it('pads single fractional digit to two', () => {
    expect(formatDecimalMoney('1234.5')).toBe('1234,50');
  });

  it('passes through two fractional digits unchanged', () => {
    expect(formatDecimalMoney('5678.00')).toBe('5678,00');
    expect(formatDecimalMoney('0.99')).toBe('0,99');
  });

  it('pads integer string with .00', () => {
    expect(formatDecimalMoney('0')).toBe('0,00');
    expect(formatDecimalMoney('1000')).toBe('1000,00');
  });

  it('truncates excess fractional digits to two', () => {
    expect(formatDecimalMoney('12.345')).toBe('12,34');
    expect(formatDecimalMoney('9.9999')).toBe('9,99');
  });

  it('handles trailing dot with no digits', () => {
    expect(formatDecimalMoney('42.')).toBe('42,00');
  });

  it('returns em dash for null', () => {
    expect(formatDecimalMoney(null)).toBe('—');
  });
});
describe('formatQuantity — a quantity of an estimate line by its unit (usability U-10)', () => {
  it('shows areas and lengths with two decimals, rounded half-up and exactly', () => {
    expect(formatQuantity('78.374', 'M2')).toBe('78,37');
    expect(formatQuantity('78.375', 'M2')).toBe('78,38');
    expect(formatQuantity('1.005', 'M2')).toBe('1,01'); // a float would give 1.00
    expect(formatQuantity('12.4', 'LM')).toBe('12,40');
    expect(formatQuantity('0.004', 'M2')).toBe('0,00');
    expect(formatQuantity('99.999', 'M2')).toBe('100,00');
  });
  it('shows hours and days with one decimal, pieces and lump sums whole', () => {
    expect(formatQuantity('7.25', 'HOUR')).toBe('7,3');
    expect(formatQuantity('2.000', 'DAY')).toBe('2,0');
    expect(formatQuantity('3.000', 'PCS')).toBe('3');
    expect(formatQuantity('1.000', 'FLAT')).toBe('1');
    expect(formatQuantity('2.5', 'PCS')).toBe('3');
  });
  it('leaves an unknown unit or a value that is not a plain decimal as it came', () => {
    expect(formatQuantity('78.374', 'XX')).toBe('78,374');
    expect(formatQuantity('78.374', null)).toBe('78,374');
    expect(formatQuantity('abc', 'M2')).toBe('abc');
    expect(formatQuantity('-1.5', 'M2')).toBe('-1,5');
  });
});

describe('signedMoneyDifference — the change of a total (usability U-8)', () => {
  it('gives the signed difference of two money strings exactly', () => {
    expect(signedMoneyDifference('2003.13', '3186.72')).toBe('+1183,59');
    expect(signedMoneyDifference('3186.72', '2003.13')).toBe('-1183,59');
    expect(signedMoneyDifference('10.00', '10.00')).toBe('0,00');
    expect(signedMoneyDifference('0.10', '0.20')).toBe('+0,10'); // 0.2 - 0.1 is not 0.1 in floats
    expect(signedMoneyDifference('5', '4.99')).toBe('-0,01');
  });
});

describe('the decimal comma of PL and RU (display) and the dot text of the API (input)', () => {
  it('shows a comma and takes both', () => {
    expect(commaDecimal('78.37')).toBe('78,37');
    expect(commaDecimal('12')).toBe('12');
    expect(dotDecimal(' 12,5 ')).toBe('12.5');
    expect(dotDecimal('12.5')).toBe('12.5');
  });

  it('every number helper of the screens speaks with the comma', () => {
    expect(formatMetric('2.7')).toBe('2,70');
    expect(formatDecimalMoney('1234.5')).toBe('1234,50');
    expect(formatQuantity('78.374', 'M2')).toBe('78,37');
    expect(signedMoneyDifference('2003.13', '3186.72')).toBe('+1183,59');
  });
});
