import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { makeMarker } from '../test/photoFixtures';
import { PointMarkerLayer } from './PointMarkerLayer';

const ATT = 'b0000000-0000-4000-8000-000000000001';

function renderLayer(props: Partial<React.ComponentProps<typeof PointMarkerLayer>> = {}, onParentClick = vi.fn()) {
  const markers = props.markers ?? [
    makeMarker(ATT, { x: 0.25, y: 0.75, label: 'rysa' }),
    makeMarker(ATT, { x: 0, y: 1, position: 1 }),
  ];
  const onSelect = vi.fn();
  render(
    <I18nProvider>
      <div onClick={onParentClick} onPointerDown={onParentClick}>
        <PointMarkerLayer markers={markers} onSelect={onSelect} {...props} />
      </div>
    </I18nProvider>,
  );
  return { markers, onSelect, onParentClick };
}

describe('PointMarkerLayer', () => {
  beforeEach(() => localStorage.clear());

  it('puts every marker at its stored fraction of the picture box (percentages, not pixels)', () => {
    renderLayer();
    const [first, second] = screen.getAllByTestId('photo-marker');
    expect(first.style.left).toBe('25%');
    expect(first.style.top).toBe('75%');
    expect(second.style.left).toBe('0%');
    expect(second.style.top).toBe('100%');
  });

  it('numbers the markers by their place in the list and names them for assistive tech (with the label when there is one)', () => {
    renderLayer();
    expect(screen.getByRole('button', { name: 'Znacznik 1: rysa' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Znacznik 2' })).toBeInTheDocument();
    expect(screen.getAllByTestId('photo-marker').map((button) => button.textContent)).toEqual(['1', '2']);
  });

  it('speaks Russian when the language is Russian', () => {
    localStorage.setItem('locale', 'ru');
    renderLayer();
    expect(screen.getByRole('button', { name: 'Метка 1: rysa' })).toBeInTheDocument();
  });

  it('a tap selects the marker and reaches nothing underneath (no full-screen, no placing, no pan)', () => {
    const { onSelect, onParentClick, markers } = renderLayer();
    const button = screen.getAllByTestId('photo-marker')[1];
    fireEvent.pointerDown(button);
    fireEvent.click(button);
    expect(onSelect).toHaveBeenCalledWith(markers[1]);
    expect(onParentClick).not.toHaveBeenCalled();
  });

  it('mobile: the button is a 44 px target around a 24 px dot, the layer itself never catches taps', () => {
    renderLayer();
    expect(screen.getByTestId('marker-layer')).toHaveClass('pointer-events-none');
    const button = screen.getAllByTestId('photo-marker')[0];
    expect(button).toHaveClass('h-11', 'w-11', 'pointer-events-auto');
    expect(button.querySelector('span')).toHaveClass('h-6', 'w-6');
    expect(button.querySelector('span')).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps the dot the same size while the picture is zoomed (scaled back by the inverse of the zoom)', () => {
    renderLayer({ inverseScale: 0.25 });
    expect(screen.getAllByTestId('photo-marker')[0].style.transform).toBe('translate(-50%, -50%) scale(0.25)');
  });

  it('marks the selected one', () => {
    const markers = [makeMarker(ATT), makeMarker(ATT, { position: 1 })];
    renderLayer({ markers, selectedId: markers[1].id });
    const dots = screen.getAllByTestId('photo-marker').map((button) => button.querySelector('span')!.className);
    expect(dots[0]).not.toContain('ring-2');
    expect(dots[1]).toContain('ring-2');
  });

  it('draws nothing for no markers', () => {
    renderLayer({ markers: [] });
    expect(screen.queryAllByTestId('photo-marker')).toHaveLength(0);
  });
});
