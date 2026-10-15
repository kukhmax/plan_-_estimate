import { describe, expect, it } from 'vitest';
import { cmToMeters, metersToCm, sanitizeCm } from './dimensions';

describe('cmToMeters', () => {
  it.each([
    ['250', '2.5'], ['90', '0.9'], ['5', '0.05'], ['0', '0'], ['100', '1'], ['1000', '10'], ['268', '2.68'], ['207.2', '2.072'],
    ['25.5', '0.255'], ['0.5', '0.005'], ['  300 ', '3'], ['25,5', '0.255'], ['-200', '-2'], ['.5', '0.005'], ['2.', '0.02'], ['007', '0.07'],
  ])('%s cm is %s m', (typed, meters) => expect(cmToMeters(typed)).toBe(meters));

  it('keeps an empty field empty and hands a non-number back untouched so the form can refuse it', () => {
    expect(cmToMeters('')).toBe('');
    expect(cmToMeters('   ')).toBe('');
    expect(cmToMeters('abc')).toBe('abc');
    expect(cmToMeters('-')).toBe('-');
    expect(cmToMeters('1.2.3')).toBe('1.2.3');
  });

  it('never goes through floating point (no 0.30000000000000004)', () => {
    for (const cm of ['30', '10', '70', '110', '230', '299', '301']) {
      expect(cmToMeters(cm)).toBe(String(Number(cm) / 100));
      expect(cmToMeters(cm)).not.toMatch(/\d{6,}/);
    }
  });
});

describe('metersToCm', () => {
  it.each([
    ['2.500', '250'], [2.7, '270'], ['0.9', '90'], ['0.05', '5'], ['2.072', '207.2'], ['2.07207', '207.207'], ['10', '1000'], ['0', '0'],
    ['2', '200'], ['-2', '-200'], ['0.255', '25.5'],
  ])('%s m is %s cm', (meters, cm) => expect(metersToCm(meters)).toBe(cm));

  it('shows nothing for nothing', () => {
    expect(metersToCm('')).toBe('');
    expect(metersToCm(null)).toBe('');
    expect(metersToCm(undefined)).toBe('');
  });

  it('is the inverse of cmToMeters', () => {
    for (const cm of ['250', '5', '90', '207.2', '25.5', '1', '10000']) expect(metersToCm(cmToMeters(cm))).toBe(cm);
  });
});

describe('sanitizeCm', () => {
  it('keeps one digit after the point and turns the comma into a point', () => {
    expect(sanitizeCm('25,55')).toBe('25.5');
    expect(sanitizeCm('250')).toBe('250');
    expect(sanitizeCm('25.')).toBe('25.');
  });
});
