import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { makeMarker } from '../test/photoFixtures';
import { cmText, markerColor, parseDistance, UTILITY_COLORS } from '../utils/photoUtilities';
import { MarkerLegend } from './MarkerLegend';
import { PointMarkerLayer } from './PointMarkerLayer';

const ATT = 'b0000000-0000-4000-8000-000000000001';

describe('the map of hidden utilities', () => {
  beforeEach(() => localStorage.setItem('locale', 'pl'));

  it('has a legend only when a marker names a utility, with the type, the label and the distances', () => {
    const plain = [makeMarker(ATT, { label: 'rysa' })];
    const { container, rerender } = render(<I18nProvider><MarkerLegend markers={plain} /></I18nProvider>);
    expect(container).toBeEmptyDOMElement();
    const markers = [
      makeMarker(ATT, { utility: 'WATER_COLD', from_floor_cm: 30, depth_cm: 3 }),
      makeMarker(ATT, { utility: 'CABLE', label: 'do gniazda', from_corner_cm: 12.5 }),
      makeMarker(ATT, { label: 'rysa' }),
      makeMarker(ATT),
    ];
    rerender(<I18nProvider><MarkerLegend markers={markers} /></I18nProvider>);
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('1Woda zimna · od podłogi 30 cm · głębokość 3 cm');
    expect(items[1]).toHaveTextContent('2Przewód elektryczny · do gniazda · od narożnika 12,5 cm');
    expect(items[2]).toHaveTextContent('3rysa');
    expect(items[3]).toHaveTextContent('4Bez podpisu');
  });

  it('colours a marker by its type, an ordinary one stays red, the contour follows', () => {
    const markers = [
      makeMarker(ATT, { utility: 'WATER_COLD', outline: [[0.1, 0.1], [0.5, 0.2], [0.9, 0.3]] }),
      makeMarker(ATT, {}),
    ];
    render(<I18nProvider><PointMarkerLayer markers={markers} onSelect={() => undefined} /></I18nProvider>);
    const dots = screen.getAllByTestId('photo-marker').map((button) => button.querySelector('span') as HTMLElement);
    expect(dots[0]).toHaveStyle({ backgroundColor: UTILITY_COLORS.WATER_COLD });
    expect(dots[1]).toHaveStyle({ backgroundColor: '#dc2626' });
    const polylines = screen.getByTestId('marker-outline').querySelectorAll('polyline');
    expect(polylines[1]).toHaveAttribute('stroke', UTILITY_COLORS.WATER_COLD);
  });

  it('reads distances: a comma, one decimal, empty is none, junk and out of range are refused', () => {
    expect(parseDistance('')).toBeNull();
    expect(parseDistance(' 30,55 ')).toBe(30.6);
    expect(parseDistance('0')).toBe(0);
    expect(parseDistance('1000')).toBe(1000);
    expect(parseDistance('1000,1')).toBeUndefined();
    expect(parseDistance('-3')).toBeUndefined();
    expect(parseDistance('x')).toBeUndefined();
    expect(cmText(2)).toBe('2');
    expect(cmText(12.5)).toBe('12,5');
    expect(markerColor({ utility: 'nope' })).toBe('#dc2626');
  });
});
