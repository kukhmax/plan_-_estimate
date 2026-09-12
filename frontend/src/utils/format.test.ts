import { describe, expect, it } from 'vitest';
import { formatMetric } from './format';

describe('formatMetric — two-decimal metric policy (Stage 7 final)', () => {
  it('renders every construction metric to exactly two decimals', () => {
    expect(formatMetric('5.000')).toBe('5.00'); // room length
    expect(formatMetric('4.900')).toBe('4.90'); // room width
    expect(formatMetric('2.700')).toBe('2.70'); // room / wall height
    expect(formatMetric('1.800')).toBe('1.80'); // opening single area
    expect(formatMetric('30.090')).toBe('30.09'); // floor area
    expect(formatMetric('12.210')).toBe('12.21'); // area segment total
    expect(formatMetric('3.000')).toBe('3.00'); // risk numeric snapshot (mm)
  });

  it('rounds three-decimal backend values to two decimals for display only', () => {
    expect(formatMetric('13.515')).toBe('13.52'); // wall 13.515 m²
    expect(formatMetric('0.005')).toBe('0.01');
    expect(formatMetric('0.004')).toBe('0.00');
  });

  it('formats numeric inputs consistently', () => {
    expect(formatMetric(5)).toBe('5.00');
    expect(formatMetric(4.9)).toBe('4.90');
    expect(formatMetric(48.6)).toBe('48.60');
    expect(formatMetric(0)).toBe('0.00');
  });

  it('renders empty and non-numeric values as an em dash', () => {
    expect(formatMetric(null)).toBe('—');
    expect(formatMetric(undefined)).toBe('—');
    expect(formatMetric('')).toBe('—');
    expect(formatMetric('abc')).toBe('—');
  });
});