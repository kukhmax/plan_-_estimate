import { describe, expect, it } from 'vitest';
import {
  calculateEffectivePrice,
  formatCoefficientSummary,
  formatPercentageDisplay,
  sumPercentages,
} from './coefficientCalculations';

describe('coefficientCalculations', () => {
  describe('sumPercentages', () => {
    it('returns 0.00 for empty array', () => {
      expect(sumPercentages([])).toBe('0.00');
    });

    it('sums single and multiple positive percentages', () => {
      expect(sumPercentages(['20.00'])).toBe('20.00');
      expect(sumPercentages(['20.00', '15.50'])).toBe('35.50');
      expect(sumPercentages(['10', '20', '30'])).toBe('60.00');
    });

    it('sums mixed positive and negative percentages', () => {
      expect(sumPercentages(['30.00', '-10.00'])).toBe('20.00');
      expect(sumPercentages(['-15.00', '-5.00'])).toBe('-20.00');
    });
  });

  describe('formatPercentageDisplay', () => {
    it('formats 0% properly', () => {
      expect(formatPercentageDisplay('0')).toBe('0%');
      expect(formatPercentageDisplay('0.00')).toBe('0%');
    });

    it('formats positive percentages with leading plus and trims trailing zeros', () => {
      expect(formatPercentageDisplay('20')).toBe('+20%');
      expect(formatPercentageDisplay('20.00')).toBe('+20%');
      expect(formatPercentageDisplay('25.50')).toBe('+25.5%');
      expect(formatPercentageDisplay('+12.34')).toBe('+12.34%');
    });

    it('formats negative percentages with leading minus', () => {
      expect(formatPercentageDisplay('-10')).toBe('-10%');
      expect(formatPercentageDisplay('-10.00')).toBe('-10%');
      expect(formatPercentageDisplay('-7.50')).toBe('-7.5%');
    });
  });

  describe('calculateEffectivePrice', () => {
    it('preserves NULL base price invariant (Do ustalenia)', () => {
      expect(calculateEffectivePrice(null, '30.00')).toBeNull();
      expect(calculateEffectivePrice(null, '0.00')).toBeNull();
    });

    it('calculates price correctly with positive adjustment', () => {
      expect(calculateEffectivePrice('45.00', '30.00')).toBe('58.50');
      expect(calculateEffectivePrice('100.00', '20.00')).toBe('120.00');
      expect(calculateEffectivePrice('50.00', '10.50')).toBe('55.25');
    });

    it('calculates price correctly with 0% adjustment', () => {
      expect(calculateEffectivePrice('45.00', '0.00')).toBe('45.00');
      expect(calculateEffectivePrice('0.00', '20.00')).toBe('0.00');
    });

    it('calculates price correctly with negative adjustment', () => {
      expect(calculateEffectivePrice('45.00', '-10.00')).toBe('40.50');
    });

    it('handles HALF_UP rounding to 2 decimal places', () => {
      // 10.55 * 1.15 = 12.1325 -> 12.13
      expect(calculateEffectivePrice('10.55', '15.00')).toBe('12.13');
      // 10.55 * 1.155 = 12.18525 -> 12.19
      expect(calculateEffectivePrice('10.55', '15.50')).toBe('12.19');
    });

    it('returns null if total percentage produces negative multiplier (< -100%)', () => {
      expect(calculateEffectivePrice('50.00', '-105.00')).toBeNull();
    });
  });

  describe('formatCoefficientSummary', () => {
    it('returns null if no options', () => {
      expect(formatCoefficientSummary([])).toBeNull();
      expect(formatCoefficientSummary(null)).toBeNull();
      expect(formatCoefficientSummary(undefined)).toBeNull();
    });

    it('returns null if only non-base 0% or empty', () => {
      expect(formatCoefficientSummary([{ percentage: '0.00', is_base: false }])).toBeNull();
    });

    it('returns 0% if explicit base option selected', () => {
      expect(formatCoefficientSummary([{ percentage: '0.00', is_base: true }])).toBe('0%');
    });

    it('returns formatted sum if non-zero percentage', () => {
      expect(
        formatCoefficientSummary([
          { percentage: '20.00', is_base: false },
          { percentage: '10.00', is_base: false },
        ]),
      ).toBe('+30%');
    });
  });
});
