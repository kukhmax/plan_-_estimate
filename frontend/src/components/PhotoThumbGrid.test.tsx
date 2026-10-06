import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { PhotoListItem } from '../types/photo';
import { makeItem } from '../test/photoFixtures';
import { GROUP_BY_DAY_THRESHOLD, PhotoThumbGrid } from './PhotoThumbGrid';

function renderGrid(items: PhotoListItem[], over: Partial<React.ComponentProps<typeof PhotoThumbGrid>> = {}) {
  const handlers = { onOpen: vi.fn(), onImageError: vi.fn(), onShowMore: vi.fn() };
  const view = render(
    <I18nProvider>
      <PhotoThumbGrid
        items={items}
        captionFor={(item) => `caption-${item.attachment.position}`}
        hasMore={false}
        loadingMore={false}
        {...handlers}
        {...over}
      />
    </I18nProvider>,
  );
  return { ...handlers, ...view };
}

describe('PhotoThumbGrid', () => {
  beforeEach(() => localStorage.clear());

  it('renders one tile per photo with its caption line under it, in the given order', () => {
    const items = [makeItem(), makeItem(), makeItem()];
    renderGrid(items);
    const tiles = screen.getAllByRole('button');
    expect(tiles).toHaveLength(3);
    const lines = items.map((item) => `caption-${item.attachment.position}`);
    lines.forEach((line) => expect(screen.getByText(line).tagName).toBe('P'));
    expect(tiles.map((tile) => tile.getAttribute('aria-label'))).toEqual(lines);
  });

  it('opens a tile by its index', () => {
    const items = [makeItem(), makeItem()];
    const { onOpen } = renderGrid(items);
    fireEvent.click(screen.getAllByRole('button')[1]);
    expect(onOpen).toHaveBeenCalledWith(1);
  });

  it('thumbnails are lazy, async-decoded, send no referrer and report load failures', () => {
    const { onImageError } = renderGrid([makeItem()]);
    const image = screen.getByRole('img');
    expect(image).toHaveAttribute('loading', 'lazy');
    expect(image).toHaveAttribute('decoding', 'async');
    expect(image).toHaveAttribute('referrerpolicy', 'no-referrer');
    fireEvent.error(image);
    expect(onImageError).toHaveBeenCalledTimes(1);
  });

  it('mobile grid: 2 columns up to 340 px, 3 above; square fixed cells; captions wrap', () => {
    const { container } = renderGrid([makeItem()]);
    expect(container.querySelector('ul')).toHaveClass('grid', 'grid-cols-2', 'min-[341px]:grid-cols-3');
    const tile = screen.getByRole('button');
    expect(tile).toHaveClass('aspect-square', 'w-full', 'overflow-hidden');
    expect(screen.getByText('caption-' + tile.getAttribute('aria-label')!.split('-')[1])).toHaveClass('break-words');
    expect(container.querySelector('li')).toHaveClass('min-w-0');
  });

  it('shows a placeholder instead of a broken image when the server sent no thumbnail URL', () => {
    renderGrid([makeItem({ thumbnail_url: null })]);
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByText('Brak podglądu')).toBeInTheDocument();
  });

  it('marks a non-default category and the report flag on the tile (PL / RU)', () => {
    const item = makeItem({ attachment: { category: 'DEFECT', include_in_report: true } });
    const { unmount } = renderGrid([item]);
    expect(screen.getByText('Wada')).toBeInTheDocument();
    expect(screen.getByText('w raporcie')).toBeInTheDocument();
    unmount();
    localStorage.setItem('locale', 'ru');
    renderGrid([item]);
    expect(screen.getByText('Дефект')).toBeInTheDocument();
    expect(screen.getByText('в отчёте')).toBeInTheDocument();
  });

  it('shows no badge for a plain GENERAL photo outside the report', () => {
    const { container } = renderGrid([makeItem()]);
    expect(container.querySelector('.bg-black\\/65')).toBeNull();
  });

  it('"show more" appears only with a next page and reflects loading', () => {
    const { rerender, onShowMore } = renderGrid([makeItem()]);
    expect(screen.queryByRole('button', { name: 'Pokaż więcej' })).toBeNull();

    rerender(
      <I18nProvider>
        <PhotoThumbGrid items={[makeItem()]} captionFor={() => 'c'} hasMore loadingMore={false} onOpen={vi.fn()} onImageError={vi.fn()} onShowMore={onShowMore} />
      </I18nProvider>,
    );
    const more = screen.getByRole('button', { name: 'Pokaż więcej' });
    expect(more).toHaveClass('min-h-11', 'w-full');
    fireEvent.click(more);
    expect(onShowMore).toHaveBeenCalledTimes(1);

    rerender(
      <I18nProvider>
        <PhotoThumbGrid items={[makeItem()]} captionFor={() => 'c'} hasMore loadingMore onOpen={vi.fn()} onImageError={vi.fn()} onShowMore={onShowMore} />
      </I18nProvider>,
    );
    expect(screen.getByRole('button', { name: 'Ładowanie zdjęć…' })).toBeDisabled();
  });

  describe('grouping by day (project-wide list, C-3)', () => {
    const day = (n: number) => `2026-06-${String(n).padStart(2, '0')}T10:00:00`;
    const many = (days: number[]) => days.map((d) => makeItem({ asset: { captured_at: day(d) } }));

    it('groups consecutive photos of one day under a sticky date line once the list is long', () => {
      const items = many([23, 23, 23, 22, 22, 22, 22, 21, 21, 21, 21, 21, 20]); // 13 > threshold
      expect(items.length).toBeGreaterThan(GROUP_BY_DAY_THRESHOLD);
      renderGrid(items, { groupByDay: true });
      const headers = screen.getAllByTestId('photo-day-header');
      expect(headers.map((h) => h.textContent)).toEqual(['23.06.2026', '22.06.2026', '21.06.2026', '20.06.2026']);
      expect(headers[0]).toHaveClass('sticky', 'top-0');
      expect(screen.getAllByRole('button')).toHaveLength(13); // nothing lost or reordered
    });

    it('keeps one flat grid for a short list', () => {
      renderGrid(many([23, 22, 21]), { groupByDay: true });
      expect(screen.queryAllByTestId('photo-day-header')).toHaveLength(0);
    });

    it('never groups when the host did not ask (room / surface / opening lists)', () => {
      renderGrid(many(Array.from({ length: 14 }, (_, i) => 1 + (i % 3))), { groupByDay: false });
      expect(screen.queryAllByTestId('photo-day-header')).toHaveLength(0);
    });

    it('does not merge non-consecutive days (the server order is respected)', () => {
      renderGrid(many([23, 22, 23, 22, 23, 22, 23, 22, 23, 22, 23, 22, 23]), { groupByDay: true });
      expect(screen.getAllByTestId('photo-day-header')).toHaveLength(13);
    });
  });
});
