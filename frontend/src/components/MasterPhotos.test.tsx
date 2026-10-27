/** V2-14b — the photos of a room on the craftsman's page: the grid, the route map with its markers and legend, the full-screen picture, a link that has run out. */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import type { PortalPhoto } from '../types/tradeLink';
import { MasterPhotos } from './MasterPhotos';

const PHOTO = (id: string, overrides: Partial<PortalPhoto> = {}): PortalPhoto => ({
  id, thumb_url: `https://files.example/${id}/thumb`, url: `https://files.example/${id}/display`, width: 1600, height: 1200, place: null, markers: [], ...overrides,
});
const MAPPED = PHOTO('m1', {
  place: 'Ściana A',
  markers: [
    { x: 0.25, y: 0.5, label: 'pod gniazdem', utility: 'CABLE', depth_cm: 4, from_floor_cm: 110, from_corner_cm: 20.5 },
    { x: 0.75, y: 0.4, label: null, utility: 'WATER_COLD', depth_cm: null, from_floor_cm: null, from_corner_cm: null },
  ],
});

function show(photos: PortalPhoto[], routeMap: PortalPhoto[], onExpired = vi.fn()) {
  render(
    <I18nProvider persist={false}>
      <MasterPhotos photos={photos} routeMap={routeMap} roomName="Salon" onExpired={onExpired} />
    </I18nProvider>,
  );
  return onExpired;
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('pl-PL');
});

describe('the photos of a room', () => {
  it('shows nothing when the room has no photo', () => {
    const { container } = render(
      <I18nProvider persist={false}>
        <MasterPhotos photos={[]} routeMap={[]} roomName="Salon" onExpired={vi.fn()} />
      </I18nProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the photos of the room in a grid with their number', () => {
    show([PHOTO('a'), PHOTO('b')], []);
    const grid = screen.getByLabelText('master-room-photos-Salon');
    expect(within(grid).getByText('Zdjęcia pomieszczenia (2)')).toBeInTheDocument();
    expect(grid.querySelectorAll('img')).toHaveLength(2);
    expect(grid.querySelector('img')).toHaveAttribute('src', 'https://files.example/a/thumb');
    expect(screen.queryByLabelText('master-route-map-Salon')).toBeNull();
  });

  it('shows the route map with numbered markers in the colours of their types and a legend with where each one lies', () => {
    show([], [MAPPED]);
    const map = screen.getByLabelText('master-route-map-Salon');
    expect(within(map).getByText('Mapa tras (1)')).toBeInTheDocument();
    expect(within(map).getByText('Ściana A')).toBeInTheDocument();
    const dots = Array.from(map.querySelectorAll('span[aria-hidden="true"][style*="left"]')) as HTMLElement[];
    expect(dots.map((d) => [d.textContent, d.style.left, d.style.top])).toEqual([['1', '25%', '50%'], ['2', '75%', '40%']]);
    expect(dots[0].style.backgroundColor).toBe('rgb(234, 88, 12)'); // the cable: orange
    expect(dots[1].style.backgroundColor).toBe('rgb(37, 99, 235)'); // cold water: blue
    expect(within(map).getByText('Przewód elektryczny · pod gniazdem · od podłogi 110 cm · od narożnika 20,5 cm · głębokość 4 cm')).toBeInTheDocument();
    expect(within(map).getByText('Woda zimna')).toBeInTheDocument();
  });
});

describe('the full picture', () => {
  it('opens the picture of a grid photo over the page and closes it', () => {
    show([PHOTO('a')], []);
    fireEvent.click(screen.getByLabelText('master-photo-a'));
    const viewer = screen.getByRole('dialog');
    expect(viewer.querySelector('img')).toHaveAttribute('src', 'https://files.example/a/display');
    fireEvent.click(screen.getByLabelText('master-photo-close'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens a map photo with its markers and legend, and closes on Escape', () => {
    show([], [MAPPED]);
    fireEvent.click(screen.getByLabelText('master-map-photo-m1'));
    const viewer = screen.getByRole('dialog');
    expect(viewer.querySelector('img')).toHaveAttribute('src', 'https://files.example/m1/display');
    expect(viewer.querySelectorAll('span[aria-hidden="true"][style*="left"]')).toHaveLength(2);
    expect(within(viewer).getByText('Woda zimna')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('says so when the link of the picture has run out and asks the page again', () => {
    const onExpired = show([PHOTO('a')], []);
    fireEvent.click(screen.getByLabelText('master-photo-a'));
    fireEvent.error(screen.getByRole('dialog').querySelector('img') as HTMLImageElement);
    expect(screen.getByText('Link do zdjęcia wygasł. Odśwież stronę.')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('master-photo-reload'));
    expect(onExpired).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
