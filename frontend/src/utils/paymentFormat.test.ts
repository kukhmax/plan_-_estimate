import { describe, expect, it } from 'vitest';
import { formatPlain, hoursAmount, percentAmount } from './paymentFormat';

// V2-9 — what the money screens read out of a number string the server sent, and what they accept in a field.

describe('formatPlain', () => {
  it('drops the empty places and keeps the owner\'s comma', () => {
    expect(formatPlain('30.00')).toBe('30');
    expect(formatPlain('37.50')).toBe('37,5');
    expect(formatPlain('7.25')).toBe('7,25');
    expect(formatPlain('120')).toBe('120');
    expect(formatPlain('-3.00')).toBe('-3');
    expect(formatPlain('0.00')).toBe('0');
  });
  it('shows a dash for nothing', () => {
    expect(formatPlain(null)).toBe('—');
    expect(formatPlain(undefined)).toBe('—');
    expect(formatPlain('')).toBe('—');
  });
});

describe('hoursAmount', () => {
  it('takes more than zero up to a day, with at most two places and a comma', () => {
    expect(hoursAmount('7,5')).toBe('7.5');
    expect(hoursAmount('24')).toBe('24');
    expect(hoursAmount('0,25')).toBe('0.25');
  });
  it('refuses zero, more than a day, three places and text', () => {
    for (const bad of ['', '0', '0,00', '24,01', '25', '1,234', 'abc', '-1']) expect(hoursAmount(bad)).toBeNull();
  });
});

describe('percentAmount', () => {
  it('takes 0,01 to 100', () => {
    expect(percentAmount('30')).toBe('30');
    expect(percentAmount('33,33')).toBe('33.33');
    expect(percentAmount('100')).toBe('100');
    expect(percentAmount('0,01')).toBe('0.01');
  });
  it('refuses zero, above 100, three places and text', () => {
    for (const bad of ['', '0', '100,01', '101', '1,234', 'x']) expect(percentAmount(bad)).toBeNull();
  });
});
