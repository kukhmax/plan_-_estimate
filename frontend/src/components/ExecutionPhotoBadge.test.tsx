import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { ProjectPhotosContext, ProjectPhotosValue } from '../hooks/ProjectPhotosContext';
import { EMPTY_PHOTO_COUNTS } from '../hooks/usePhotoCounts';
import { PhotoCounts } from '../types/photo';
import { EXECUTION_ROW_WITH_BADGE, ExecutionPhotoBadge, INSPECT_BUTTON_WITH_BADGE, InspectionPhotoBadge } from './ExecutionPhotoBadge';

const SURFACE = '33333333-3333-4333-8333-333333333333';
const OTHER = '44444444-4444-4444-8444-444444444444';

function renderBadge(counts: Partial<PhotoCounts> | null, surfaceId = SURFACE) {
  const value: ProjectPhotosValue | null =
    counts === null
      ? null
      : {
          projectId: 'p',
          counts: { ...EMPTY_PHOTO_COUNTS, ...counts },
          isExpanded: () => false,
          toggle: () => {},
          adjust: () => {},
          resolveLocation: () => '',
          ensureLocations: () => {},
        };
  return render(
    <I18nProvider>
      <ProjectPhotosContext.Provider value={value}>
        <ExecutionPhotoBadge surfaceId={surfaceId} />
      </ProjectPhotosContext.Provider>
    </I18nProvider>,
  );
}

describe('ExecutionPhotoBadge', () => {
  beforeEach(() => localStorage.clear());

  it('shows a camera and the number of execution photos of THIS surface', () => {
    renderBadge({ work_surfaces: { [SURFACE]: 2, [OTHER]: 9 } });
    const badge = screen.getByTestId('execution-photo-badge');
    expect(badge).toHaveTextContent('2');
    expect(badge.querySelector('svg')).not.toBeNull();
  });

  it('names itself for assistive tech and as a tooltip, in the language of the app', () => {
    renderBadge({ work_surfaces: { [SURFACE]: 3 } });
    const badge = screen.getByRole('img', { name: 'Zdjęcia wykonania: 3' });
    expect(badge).toHaveAttribute('title', 'Zdjęcia wykonania: 3');
  });

  it('speaks Russian', () => {
    localStorage.setItem('locale', 'ru');
    renderBadge({ work_surfaces: { [SURFACE]: 3 } });
    expect(screen.getByRole('img', { name: 'Фото выполнения: 3' })).toBeInTheDocument();
  });

  it('counts only execution photos: surface, room, object and inspection photos do not make it appear', () => {
    renderBadge({ project: 7, surfaces: { [SURFACE]: 4 }, room_totals: { [SURFACE]: 4 }, inspections: { [SURFACE]: 2 }, works: { k: 3 } });
    expect(screen.queryByTestId('execution-photo-badge')).toBeNull();
  });

  it('draws nothing for no photos, for another surface\'s photos, or outside a project photo context', () => {
    renderBadge({ work_surfaces: { [SURFACE]: 0 } });
    expect(screen.queryByTestId('execution-photo-badge')).toBeNull();
    renderBadge({ work_surfaces: { [OTHER]: 5 } });
    expect(screen.queryByTestId('execution-photo-badge')).toBeNull();
    renderBadge(null);
    expect(screen.queryByTestId('execution-photo-badge')).toBeNull();
  });

  it('is a mark, not a control: it takes no taps and sits in the row after the label', () => {
    renderBadge({ work_surfaces: { [SURFACE]: 1 } });
    const badge = screen.getByTestId('execution-photo-badge');
    expect(badge).toHaveClass('pointer-events-none', 'inline-flex', 'shrink-0');
    expect(badge).not.toHaveClass('absolute');
    expect(badge.tagName).toBe('SPAN');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('the row is a wrapping flex line: the label and the mark share it, and when they do not fit the mark drops below the label instead of running under it', () => {
    expect(EXECUTION_ROW_WITH_BADGE.split(' ')).toEqual(expect.arrayContaining(['flex', 'flex-wrap', 'items-center', 'justify-center']));
  });
});

describe('InspectionPhotoBadge', () => {
  beforeEach(() => localStorage.clear());

  const renderInspection = (counts: Partial<PhotoCounts> | null, surfaceId: string | null = SURFACE, plane?: { roomId: string; plane: 'FLOOR' | 'CEILING' }) => {
    const value: ProjectPhotosValue | null =
      counts === null
        ? null
        : {
            projectId: 'p', counts: { ...EMPTY_PHOTO_COUNTS, ...counts }, isExpanded: () => false, toggle: () => {},
            adjust: () => {}, resolveLocation: () => '', ensureLocations: () => {},
          };
    return render(
      <I18nProvider>
        <ProjectPhotosContext.Provider value={value}>
          <InspectionPhotoBadge surfaceId={surfaceId} roomId={plane?.roomId} plane={plane?.plane} />
        </ProjectPhotosContext.Provider>
      </I18nProvider>,
    );
  };

  it('shows a camera and the number of inspection photos of THIS surface', () => {
    renderInspection({ inspection_surfaces: { [SURFACE]: 5, [OTHER]: 9 } });
    const badge = screen.getByTestId('inspection-photo-badge');
    expect(badge).toHaveTextContent('5');
    expect(badge.querySelector('svg')).not.toBeNull();
    expect(screen.queryByTestId('execution-photo-badge')).toBeNull();
  });

  it('a floor / ceiling inspection is counted per room and plane (no surface), and the other plane or room is not', () => {
    const counts = { inspection_planes: { room1: { CEILING: 4, FLOOR: 1 }, room2: { CEILING: 9 } } };
    const { unmount } = renderInspection(counts, null, { roomId: 'room1', plane: 'CEILING' });
    expect(screen.getByTestId('inspection-photo-badge')).toHaveTextContent('4');
    unmount();
    const floor = renderInspection(counts, null, { roomId: 'room1', plane: 'FLOOR' });
    expect(screen.getByTestId('inspection-photo-badge')).toHaveTextContent('1');
    floor.unmount();
    renderInspection({ inspection_planes: { room2: { CEILING: 9 } } }, null, { roomId: 'room1', plane: 'CEILING' });
    expect(screen.queryByTestId('inspection-photo-badge')).toBeNull();
  });

  it('adds the surface and the plane numbers when both exist, and ignores the plane without a room', () => {
    const counts = { inspection_surfaces: { [SURFACE]: 2 }, inspection_planes: { room1: { CEILING: 4 } } };
    const { unmount } = renderInspection(counts, SURFACE, { roomId: 'room1', plane: 'CEILING' });
    expect(screen.getByTestId('inspection-photo-badge')).toHaveTextContent('6');
    unmount();
    renderInspection(counts, null);
    expect(screen.queryByTestId('inspection-photo-badge')).toBeNull();
  });

  it('names itself in Polish and in Russian', () => {
    const { unmount } = renderInspection({ inspection_surfaces: { [SURFACE]: 2 } });
    expect(screen.getByRole('img', { name: 'Zdjęcia z badania: 2' })).toHaveAttribute('title', 'Zdjęcia z badania: 2');
    unmount();
    localStorage.setItem('locale', 'ru');
    renderInspection({ inspection_surfaces: { [SURFACE]: 2 } });
    expect(screen.getByRole('img', { name: 'Фото обследования: 2' })).toBeInTheDocument();
  });

  it('counts only inspection photos of the surface: surface, execution, per-inspection and object photos do not show it', () => {
    renderInspection({ project: 3, surfaces: { [SURFACE]: 4 }, work_surfaces: { [SURFACE]: 4 }, inspections: { [SURFACE]: 4 } });
    expect(screen.queryByTestId('inspection-photo-badge')).toBeNull();
  });

  it('draws nothing for no photos, other surfaces, or outside a project photo context', () => {
    renderInspection({ inspection_surfaces: { [SURFACE]: 0 } });
    expect(screen.queryByTestId('inspection-photo-badge')).toBeNull();
    renderInspection({ inspection_surfaces: { [OTHER]: 2 } });
    expect(screen.queryByTestId('inspection-photo-badge')).toBeNull();
    renderInspection(null);
    expect(screen.queryByTestId('inspection-photo-badge')).toBeNull();
  });

  it('is a mark, not a control, next to the label of a half-width button', () => {
    renderInspection({ inspection_surfaces: { [SURFACE]: 1 } });
    const badge = screen.getByTestId('inspection-photo-badge');
    expect(badge).toHaveClass('pointer-events-none', 'inline-flex', 'shrink-0');
    expect(badge).not.toHaveClass('absolute');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('the half-width button wraps the same way (a tighter gap), so a long Russian label is never cut in the middle of a word', () => {
    expect(INSPECT_BUTTON_WITH_BADGE.split(' ')).toEqual(expect.arrayContaining(['flex', 'flex-wrap', 'items-center', 'justify-center']));
  });
});

describe('badge number display', () => {
  beforeEach(() => localStorage.clear());
  const show = (n: number) => {
    const value: ProjectPhotosValue = {
      projectId: 'p', counts: { ...EMPTY_PHOTO_COUNTS, work_surfaces: { [SURFACE]: n }, inspection_surfaces: { [SURFACE]: n } },
      isExpanded: () => false, toggle: () => {}, adjust: () => {}, resolveLocation: () => '', ensureLocations: () => {},
    };
    return render(
      <I18nProvider>
        <ProjectPhotosContext.Provider value={value}>
          <ExecutionPhotoBadge surfaceId={SURFACE} />
          <InspectionPhotoBadge surfaceId={SURFACE} />
        </ProjectPhotosContext.Provider>
      </I18nProvider>,
    );
  };

  it('shows the exact number up to 99', () => {
    show(99);
    expect(screen.getByTestId('execution-photo-badge')).toHaveTextContent('99');
    expect(screen.getByTestId('execution-photo-badge')).not.toHaveTextContent('99+');
    expect(screen.getByTestId('inspection-photo-badge')).toHaveTextContent('99');
  });

  it('shows 99+ above that, in the mark only: the spoken name keeps the real number', () => {
    show(1250);
    for (const id of ['execution-photo-badge', 'inspection-photo-badge']) {
      expect(screen.getByTestId(id)).toHaveTextContent('99+');
    }
    expect(screen.getByRole('img', { name: 'Zdjęcia wykonania: 1250' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Zdjęcia z badania: 1250' })).toBeInTheDocument();
  });
});

