/**
 * Stage 14H.2 — photos in Realizacja: one photo button per planned work (counted by its occurrence key, collapsed),
 * the category suggested by the work's status, the list of evidence of works that left the plan, the plan reloaded when
 * an upload is refused because its work is gone, and PL / RU, touch targets and theme-safe styling.
 * The section itself is mocked: its listing / uploading behaviour is covered by PhotoSection.test.tsx.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api/http';
import * as photosApi from './api/photos';
import * as priceItemsApi from './api/priceItems';
import * as workPlansApi from './api/workPlans';
import { SurfaceExecutionView } from './components/SurfaceExecutionView';
import { ProjectPhotosContext, ProjectPhotosValue, photoKey } from './hooks/ProjectPhotosContext';
import { I18nProvider } from './hooks/useI18n';
import { getPhotoUploadQueue, resetPhotoUploadQueue } from './hooks/usePhotoUploadQueue';
import { jpegFile, jpegWithExif } from './test/jpegFixtures';
import { makeItem } from './test/photoFixtures';
import { PhotoCounts } from './types/photo';
import {
  PlannedWorkExecutionRead,
  SurfacePlannedWorkRead,
  SurfacePriceItemSummaryRead,
  SurfaceWorkPlanRead,
} from './types/workPlan';

vi.mock('./api/workPlans', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/workPlans')>();
  return { ...actual, fetchSurfaceWorkPlan: vi.fn(), transitionWorkExecution: vi.fn() };
});
vi.mock('./api/priceItems', () => ({ fetchPriceItems: vi.fn() }));
vi.mock('./api/photos', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/photos')>();
  return { ...actual, uploadPhoto: vi.fn(), fetchPhoto: vi.fn() };
});

const sectionProps = vi.fn();
vi.mock('./components/PhotoSection', () => ({
  PhotoSection: (props: Record<string, unknown>) => {
    sectionProps(props);
    return <div data-testid="photo-section" />;
  },
}));

const S = 's-1';
const NS: PlannedWorkExecutionRead = { status: 'NOT_STARTED', started_at: null, completed_at: null, ready_after: null };
const IP: PlannedWorkExecutionRead = { status: 'IN_PROGRESS', started_at: '2026-09-27T08:00:00Z', completed_at: null, ready_after: null };
const DONE: PlannedWorkExecutionRead = {
  status: 'COMPLETED',
  started_at: '2026-09-27T08:00:00Z',
  completed_at: '2026-09-27T10:00:00Z',
  ready_after: null,
};

function item(id: string, name: string): SurfacePriceItemSummaryRead {
  return {
    id, code: id.toUpperCase(), name_key: null, display_name: name, category: 'SKIM_COAT', unit: 'M2',
    price_scope: 'LABOR', price: '10.00', currency: 'PLN', is_archived: false, quality_level: null,
  };
}

function work(key: string, position: number, execution: PlannedWorkExecutionRead, priceItem = item('p1', 'Gładź')): SurfacePlannedWorkRead {
  return {
    id: `row-${key}`, work_plan_id: 'plan-1', price_item_id: priceItem.id, position, occurrence_key: key,
    wait_after_hours: null, price_item: priceItem, coefficient_options: [], execution,
  };
}

function plan(works: SurfacePlannedWorkRead[]): SurfaceWorkPlanRead {
  return { id: 'plan-1', surface_id: S, substrate: 'CONCRETE', quality_target: 'S2', planned_works: works, template_applications: [] };
}

const PLAN = plan([
  work('k-ns', 0, NS, item('p0', 'Gruntowanie')),
  work('k-ip', 1, IP),
  work('k-done', 2, DONE, item('p2', 'Malowanie')),
]);

const BASE: PhotoCounts = {
  project: 0, rooms: {}, surfaces: { [S]: 7 }, openings: {}, room_totals: { r: 7 },
  inspections: {}, findings: {}, lineages: {}, questions: {},
  // k-ns 2, k-done 1, plus 3 photos of a work that is no longer in the plan
  works: { 'k-ns': 2, 'k-done': 1, 'k-old': 3 },
  work_surfaces: { [S]: 6 },
  inspection_surfaces: {},
};

function provided(over: Partial<ProjectPhotosValue> = {}, expanded: string[] = []): ProjectPhotosValue {
  return {
    projectId: 'p',
    counts: BASE,
    isExpanded: (key) => expanded.includes(key),
    toggle: vi.fn(),
    adjust: vi.fn(),
    resolveLocation: vi.fn(() => 'x'),
    ensureLocations: vi.fn(),
    ...over,
  };
}

function renderView(value: ProjectPhotosValue | null = provided()) {
  return render(
    <I18nProvider>
      <ProjectPhotosContext.Provider value={value}>
        <SurfaceExecutionView projectId="p" roomId="r" surfaceId={S} surfaceName="Ściana A" onClose={vi.fn()} />
      </ProjectPhotosContext.Provider>
    </I18nProvider>,
  );
}

const card = (key: string) => screen.getByLabelText(`execution-card-${key}`);
const lastSection = () => sectionProps.mock.calls[sectionProps.mock.calls.length - 1][0] as Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(workPlansApi.fetchSurfaceWorkPlan).mockResolvedValue(PLAN);
  vi.mocked(priceItemsApi.fetchPriceItems).mockResolvedValue({
    items: [
      { ...item('p-old', 'Frezowanie'), is_archived: true, created_at: '', updated_at: '' },
      { ...item('p1', 'Gładź'), created_at: '', updated_at: '' },
    ],
    total: 2,
  } as never);
});

afterEach(() => {
  resetPhotoUploadQueue();
});

describe('the photo button of each work', () => {
  it('every card has its own button, counted by the work\'s occurrence key, collapsed until pressed', async () => {
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    expect(within(card('k-ns')).getByRole('button', { name: 'Zdjęcia: 2' })).toBeInTheDocument();
    expect(within(card('k-ip')).getByRole('button', { name: 'Zdjęcia: 0' })).toBeInTheDocument();
    expect(within(card('k-done')).getByRole('button', { name: 'Zdjęcia: 1' })).toBeInTheDocument();
    expect(screen.queryByTestId('photo-section')).toBeNull(); // nothing is read while collapsed
  });

  it('pressing it opens that work\'s section under a key of its own', async () => {
    const toggle = vi.fn();
    renderView(provided({ toggle }));
    await screen.findByLabelText(`execution-works-${S}`);
    fireEvent.click(within(card('k-ip')).getByRole('button', { name: 'Zdjęcia: 0' }));
    expect(toggle).toHaveBeenCalledWith(photoKey('WORK', S, 'k-ip'));
  });

  it.each([
    ['k-ns', 'BEFORE', 'Gruntowanie'],
    ['k-ip', 'IN_PROGRESS', 'Gładź'],
    ['k-done', 'AFTER', 'Malowanie'],
  ] as const)('%s: the section suggests the category %s and names the operation', async (key, category, label) => {
    renderView(provided({}, [photoKey('WORK', S, key)]));
    await screen.findByLabelText(`execution-works-${S}`);
    const props = lastSection();
    expect(props).toMatchObject({ context: 'WORK', targetId: S, occurrenceKey: key, defaultCategory: category, allowUpload: true });
    const caption = props.locationLabel as string;
    expect(caption).toContain('Ściana A');
    expect(caption).toContain(label);
  });

  it('opens one work at a time per key: another work\'s section stays closed', async () => {
    renderView(provided({}, [photoKey('WORK', S, 'k-ip')]));
    await screen.findByLabelText(`execution-works-${S}`);
    expect(screen.getAllByTestId('photo-section')).toHaveLength(1);
    expect(lastSection()).toMatchObject({ occurrenceKey: 'k-ip' });
  });

  it('the button sits with the status badge, never beside the name, and is a 44 px control', async () => {
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    const button = within(card('k-ns')).getByRole('button', { name: 'Zdjęcia: 2' });
    expect(button.className).toMatch(/min-h-11/);
    const badge = screen.getByLabelText('execution-status-k-ns');
    expect(button.parentElement).toBe(badge.parentElement); // same row: wraps below a long name instead of squeezing it
    expect(button.parentElement?.className).toContain('flex-wrap');
    expect(button.parentElement?.querySelector('p')).toBeNull();
  });

  it('shows nothing about photos outside a project photo context (existing screens)', async () => {
    renderView(null);
    await screen.findByLabelText(`execution-works-${S}`);
    expect(screen.queryByRole('button', { name: /Zdjęcia: / })).toBeNull();
    expect(screen.queryByLabelText(`execution-detached-photos-${S}`)).toBeNull();
  });

  it('the execution actions keep working beside the photo button', async () => {
    vi.mocked(workPlansApi.transitionWorkExecution).mockResolvedValue({ occurrence_key: 'k-ns', ...IP });
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    fireEvent.click(screen.getByLabelText('execution-start-k-ns'));
    await waitFor(() => expect(screen.getByLabelText('execution-status-k-ns')).toHaveTextContent('W trakcie'));
  });
});

describe('evidence of works that left the plan', () => {
  it('appears with the number of photos whose work is no longer planned (surface total minus the plan\'s works)', async () => {
    renderView();
    const block = await screen.findByLabelText(`execution-detached-photos-${S}`);
    expect(block).toHaveTextContent('Zdjęcia dawnych prac');
    expect(block).toHaveTextContent('Prace usunięte lub zastąpione w planie');
    expect(within(block).getByRole('button', { name: 'Zdjęcia: 3' })).toBeInTheDocument();
    expect(screen.queryByTestId('photo-section')).toBeNull();
  });

  it('is hidden when every photo belongs to a planned work', async () => {
    renderView(provided({ counts: { ...BASE, works: { 'k-ns': 2, 'k-done': 1 }, work_surfaces: { [S]: 3 } } }));
    await screen.findByLabelText(`execution-works-${S}`);
    expect(screen.queryByLabelText(`execution-detached-photos-${S}`)).toBeNull();
  });

  it('is hidden when the surface has no execution photo at all', async () => {
    renderView(provided({ counts: { ...BASE, works: {}, work_surfaces: {}, inspection_surfaces: {} } }));
    await screen.findByLabelText(`execution-works-${S}`);
    expect(screen.queryByLabelText(`execution-detached-photos-${S}`)).toBeNull();
  });

  it('opens a view-only list of the surface that leaves out the plan\'s works', async () => {
    const toggle = vi.fn();
    const { unmount } = renderView(provided({ toggle }));
    fireEvent.click(within(await screen.findByLabelText(`execution-detached-photos-${S}`)).getByRole('button', { name: 'Zdjęcia: 3' }));
    expect(toggle).toHaveBeenCalledWith(photoKey('WORK', S, 'detached'));
    unmount();

    renderView(provided({}, [photoKey('WORK', S, 'detached')]));
    await screen.findByLabelText(`execution-works-${S}`);
    const props = lastSection();
    expect(props).toMatchObject({ context: 'WORK', targetId: S, projectId: 'p' });
    expect(props.occurrenceKey).toBeUndefined();
    expect(props.allowUpload).toBeUndefined(); // no picker: nothing can be attached to a work that is no longer planned
    expect([...(props.excludeKeys as Set<string>)].sort()).toEqual(['k-done', 'k-ip', 'k-ns']);
  });

  it('labels each photo with the operation snapshotted on it, archived Price Book items included', async () => {
    renderView(provided({}, [photoKey('WORK', S, 'detached')]));
    await screen.findByLabelText(`execution-works-${S}`);
    await waitFor(() => expect(priceItemsApi.fetchPriceItems).toHaveBeenCalledWith({ archived: 'all' }));
    const label = () => (lastSection().locationLabel as (a: unknown) => string)(
      makeItem({ attachment: { context: 'WORK', room_id: null, surface_id: S, occurrence_key: 'k-old', price_item_id: 'p-old' } }).attachment,
    );
    await waitFor(() => expect(label()).toContain('Frezowanie'));
    expect(label()).toContain('Ściana A');
    // an operation that cannot be named gets the neutral text, never an empty caption or an id
    const unknown = (lastSection().locationLabel as (a: unknown) => string)(
      makeItem({ attachment: { context: 'WORK', room_id: null, surface_id: S, occurrence_key: 'k-old', price_item_id: 'gone' } }).attachment,
    );
    expect(unknown).toContain('Pozycja cennika jest niedostępna');
  });

  it('the Price Book is read only when the list is opened', async () => {
    renderView();
    await screen.findByLabelText(`execution-detached-photos-${S}`);
    expect(priceItemsApi.fetchPriceItems).not.toHaveBeenCalled();
  });

  it('keeps its open list on screen when the last photo of it is archived, until it is closed', async () => {
    renderView(provided({ counts: { ...BASE, works: { 'k-ns': 2, 'k-done': 1 }, work_surfaces: { [S]: 3 } } }, [photoKey('WORK', S, 'detached')]));
    await screen.findByLabelText(`execution-works-${S}`);
    expect(screen.getByLabelText(`execution-detached-photos-${S}`)).toBeInTheDocument();
    expect(within(screen.getByLabelText(`execution-detached-photos-${S}`)).getByRole('button', { name: 'Zdjęcia: 0' })).toBeInTheDocument();
  });

  it('the exclusion list follows the plan that is on screen (a work of the plan never counts as detached)', async () => {
    const { rerender } = renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    sectionProps.mockClear();
    rerender(
      <I18nProvider>
        <ProjectPhotosContext.Provider value={provided({}, [photoKey('WORK', S, 'detached')])}>
          <SurfaceExecutionView projectId="p" roomId="r" surfaceId={S} surfaceName="Ściana A" onClose={vi.fn()} />
        </ProjectPhotosContext.Provider>
      </I18nProvider>,
    );
    await waitFor(() => expect(sectionProps).toHaveBeenCalled());
    expect((lastSection().excludeKeys as Set<string>).has('k-ns')).toBe(true);
  });
});

describe('an upload refused because the work left the plan', () => {
  const failUpload = async (target: Record<string, string>) => {
    vi.mocked(photosApi.uploadPhoto).mockRejectedValue(new ApiError('gone', 409, 'WORK_OCCURRENCE_NOT_CURRENT'));
    await act(async () => {
      getPhotoUploadQueue().enqueue(
        [jpegFile('w.jpg', jpegWithExif({ original: new Date() }))],
        { projectId: 'p', context: 'WORK', ...target },
        'GALLERY',
      );
    });
  };

  it('reads the plan again for the surface it belongs to', async () => {
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(1);
    await failUpload({ surfaceId: S, occurrenceKey: 'k-ns' });
    await waitFor(() => expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(2));
  });

  it('leaves the plan of another surface alone', async () => {
    renderView();
    await screen.findByLabelText(`execution-works-${S}`);
    await failUpload({ surfaceId: 'other-surface', occurrenceKey: 'k-x' });
    await waitFor(() => expect(photosApi.uploadPhoto).toHaveBeenCalled());
    await act(async () => undefined);
    expect(workPlansApi.fetchSurfaceWorkPlan).toHaveBeenCalledTimes(1);
  });
});

describe('locales and styling', () => {
  it('renders the detached list in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderView();
    const block = await screen.findByLabelText(`execution-detached-photos-${S}`);
    expect(block).toHaveTextContent('Фото прежних работ');
    expect(block).toHaveTextContent('Работы, удалённые или заменённые в плане');
    expect(within(card('k-ns')).getByRole('button', { name: /2/ })).toBeInTheDocument();
  });

  it('uses theme tokens only (no light-only colours) and wraps long text', async () => {
    renderView();
    const block = await screen.findByLabelText(`execution-detached-photos-${S}`);
    expect(block.innerHTML).not.toMatch(/bg-white|bg-slate-|text-slate-|bg-gray-|text-gray-/);
    expect(block.querySelector('p.break-words')).not.toBeNull();
    for (const button of block.querySelectorAll('button')) expect(button.className).toMatch(/min-h-11/);
  });
});
