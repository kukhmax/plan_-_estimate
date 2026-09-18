import { describe, expect, it } from 'vitest';
import { addDecimalStrings, sumDecimalStrings } from './decimalArithmetic';

describe('addDecimalStrings', () => {
  it('adds two integer strings', () => {
    expect(addDecimalStrings('100', '200')).toBe('300');
  });

  it('adds two decimal strings with same scale', () => {
    expect(addDecimalStrings('12.50', '3.25')).toBe('15.75');
  });

  it('preserves max scale from both inputs', () => {
    expect(addDecimalStrings('10.647', '10.647')).toBe('21.294');
  });

  it('no floating point error: 319.41 + 319.41', () => {
    expect(addDecimalStrings('319.41', '319.41')).toBe('638.82');
  });

  it('no floating point error: repeated addition of 319.41 four times', () => {
    const s = addDecimalStrings(addDecimalStrings(addDecimalStrings('319.41', '319.41'), '319.41'), '319.41');
    expect(s).toBe('1277.64');
  });

  it('handles zero integer + decimal', () => {
    expect(addDecimalStrings('0', '5.00')).toBe('5.00');
  });

  it('handles mixed integer and decimal input', () => {
    expect(addDecimalStrings('5', '3.14')).toBe('8.14');
  });

  it('handles three decimal places', () => {
    expect(addDecimalStrings('1.000', '2.000')).toBe('3.000');
  });

  it('no floating point error: 0.1 + 0.2', () => {
    expect(addDecimalStrings('0.1', '0.2')).toBe('0.3');
  });

  it('adds large values without overflow', () => {
    expect(addDecimalStrings('99999.99', '0.01')).toBe('100000.00');
  });
});

describe('sumDecimalStrings', () => {
  it('sums a single-element array unchanged', () => {
    expect(sumDecimalStrings(['42.00'])).toBe('42.00');
  });

  it('sums two values', () => {
    expect(sumDecimalStrings(['10.00', '20.00'])).toBe('30.00');
  });

  it('sums four identical values exactly (no float drift)', () => {
    expect(sumDecimalStrings(['319.41', '319.41', '319.41', '319.41'])).toBe('1277.64');
  });

  it('sums values with different decimal scales', () => {
    expect(sumDecimalStrings(['1.1', '2.22', '3.333'])).toBe('6.653');
  });

  it('sums three round values', () => {
    expect(sumDecimalStrings(['10.00', '20.00', '30.00'])).toBe('60.00');
  });

  it('sums quantities typical for estimate lines', () => {
    expect(sumDecimalStrings(['12.500', '8.250', '6.000'])).toBe('26.750');
  });
});
