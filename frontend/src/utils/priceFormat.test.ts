import { describe, expect, it } from 'vitest';
import { formatPrice, normalizePriceInput } from './priceFormat';

describe('formatPrice — PLN money display without float arithmetic (Stage 9D)', () => {
  it('renders exactly two decimals with a comma separator', () => {
    expect(formatPrice('45')).toBe('45,00');
    expect(formatPrice('45.5')).toBe('45,50');
    expect(formatPrice('45.50')).toBe('45,50');
    expect(formatPrice('0')).toBe('0,00');
    expect(formatPrice('0.00')).toBe('0,00');
    expect(formatPrice('1.11')).toBe('1,11');
    expect(formatPrice('9.99')).toBe('9,99');
    expect(formatPrice('250')).toBe('250,00');
  });

  it('never rounds or truncates the stored value', () => {
    expect(formatPrice('45.555')).toBe('45,55'); // display only, value never sent
    expect(formatPrice('1234.56')).toBe('1234,56');
    expect(formatPrice('999999.99')).toBe('999999,99');
  });

  it('renders empty values as an em dash', () => {
    expect(formatPrice(null)).toBe('—');
    expect(formatPrice(undefined)).toBe('—');
    expect(formatPrice('')).toBe('—');
  });
});

describe('normalizePriceInput — price input contract (Stage 9D)', () => {
  it.each([
    ['45', '45'],
    ['45.5', '45.5'],
    ['45.50', '45.50'],
    ['0', '0'],
    ['0.00', '0.00'],
    [' 45 ', '45'],
  ])('accepts "%s" canonically as "%s"', (raw, expected) => {
    const state = normalizePriceInput(raw);
    expect(state.ok).toBe(true);
    expect(state.value).toBe(expected);
  });

  it('normalizes a comma decimal separator to a dot', () => {
    expect(normalizePriceInput('45,5')).toEqual({ ok: true, reason: null, value: '45.5' });
    expect(normalizePriceInput('45,50')).toEqual({ ok: true, reason: null, value: '45.50' });
  });

  it.each([
    ['45.555', 'precision'],
    ['45,555', 'precision'],
    ['0.12345', 'precision'],
  ])('rejects "%s" with a precision error (no silent truncation)', (raw, reason) => {
    expect(normalizePriceInput(raw)).toEqual({
      ok: false,
      reason,
      value: null,
    });
  });

  it('rejects negative values', () => {
    expect(normalizePriceInput('-1')).toMatchObject({ ok: false, reason: 'negative' });
    expect(normalizePriceInput('-0.01')).toMatchObject({ ok: false, reason: 'negative' });
  });

  it.each(['abc', '45.5.5', '1,2,3', '4..5', '45.'])(
    'rejects malformed text "%s"',
    (raw) => {
      expect(normalizePriceInput(raw)).toMatchObject({ ok: false, reason: 'format' });
    },
  );

  it('treats empty input as empty (required)', () => {
    expect(normalizePriceInput('')).toEqual({ ok: false, reason: 'empty', value: null });
    expect(normalizePriceInput('   ')).toEqual({ ok: false, reason: 'empty', value: null });
  });
});