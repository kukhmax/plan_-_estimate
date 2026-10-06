import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { ProjectPhotosContext, ProjectPhotosValue, photoKey } from '../hooks/ProjectPhotosContext';
import { PhotoCounts } from '../types/photo';
import { PhotoCardButton, PhotoCardPanel } from './PhotoCard';

const sectionProps = vi.fn();
vi.mock('./PhotoSection', () => ({
  PhotoSection: (props: Record<string, unknown>) => {
    sectionProps(props);
    return <div data-testid="photo-section" />;
  },
}));

const COUNTS: PhotoCounts = { project: 1, rooms: { r1: 2 }, surfaces: { s1: 3 }, openings: { o1: 4 } };

function value(over: Partial<ProjectPhotosValue> = {}, expanded: string[] = []): ProjectPhotosValue {
  return {
    projectId: 'p1',
    counts: COUNTS,
    isExpanded: (key) => expanded.includes(key),
    toggle: vi.fn(),
    adjust: vi.fn(),
    resolveLocation: vi.fn(() => 'resolved'),
    ensureLocations: vi.fn(),
    ...over,
  };
}

function renderWith(ui: React.ReactNode, provided: ProjectPhotosValue | null) {
  return render(
    <I18nProvider>
      <ProjectPhotosContext.Provider value={provided}>{ui}</ProjectPhotosContext.Provider>
    </I18nProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  sectionProps.mockClear();
});

describe('without a project photo context (existing screens and tests)', () => {
  it('renders nothing at all — not even an empty row', () => {
    const { container } = renderWith(
      <>
        <PhotoCardButton context="ROOM" targetId="r1" rowClassName="flex justify-end" />
        <PhotoCardPanel context="ROOM" targetId="r1" />
      </>,
      null,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('PhotoCardButton', () => {
  it.each([
    ['ROOM', 'r1', 'Zdjęcia: 2'],
    ['SURFACE', 's1', 'Zdjęcia: 3'],
    ['OPENING', 'o1', 'Zdjęcia: 4'],
    ['ROOM', 'unknown', 'Zdjęcia: 0'],
  ] as const)('%s %s shows its own count', (context, targetId, name) => {
    renderWith(<PhotoCardButton context={context} targetId={targetId} />, value());
    expect(screen.getByRole('button', { name })).toBeInTheDocument();
  });

  it('the object button shows the total of every photo of the object (C-3)', () => {
    renderWith(<PhotoCardButton context="PROJECT" />, value());
    expect(screen.getByRole('button', { name: 'Zdjęcia: 10' })).toBeInTheDocument();
  });

  it('reflects the expanded state and toggles by its key', () => {
    const provided = value({}, [photoKey('SURFACE', 's1')]);
    renderWith(<PhotoCardButton context="SURFACE" targetId="s1" />, provided);
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(button);
    expect(provided.toggle).toHaveBeenCalledWith('SURFACE:s1');
  });

  it('can sit on a row of its own', () => {
    const { container } = renderWith(
      <PhotoCardButton context="SURFACE" targetId="s1" rowClassName="flex justify-end" />,
      value(),
    );
    expect(container.firstElementChild).toHaveClass('flex', 'justify-end');
    expect(container.firstElementChild?.firstElementChild?.tagName).toBe('BUTTON');
  });
});

describe('PhotoCardPanel', () => {
  it('mounts the section only while expanded (nothing is fetched while collapsed)', () => {
    renderWith(<PhotoCardPanel context="ROOM" targetId="r1" locationSegments={['Salon']} />, value());
    expect(screen.queryByTestId('photo-section')).toBeNull();
    expect(sectionProps).not.toHaveBeenCalled();
  });

  it('passes the target, the host names as a fixed location and the count callback', () => {
    const provided = value({}, [photoKey('SURFACE', 's1')]);
    renderWith(<PhotoCardPanel context="SURFACE" targetId="s1" locationSegments={['Salon', 'Ściana 1']} />, provided);
    expect(sectionProps).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: 'p1',
        context: 'SURFACE',
        targetId: 's1',
        locationLabel: 'Salon → Ściana 1',
        onCountAdjust: provided.adjust,
      }),
    );
  });

  it('writes a dash for a host name that is missing', () => {
    renderWith(<PhotoCardPanel context="SURFACE" targetId="s1" locationSegments={[undefined, 'Ściana 1']} />, value({}, ['SURFACE:s1']));
    expect(sectionProps.mock.calls[0][0].locationLabel).toBe('— → Ściana 1');
  });

  it('the object panel resolves each photo through the context and loads the names when it opens', () => {
    const provided = value({}, [photoKey('PROJECT')]);
    renderWith(<PhotoCardPanel context="PROJECT" />, provided);
    expect(sectionProps.mock.calls[0][0].locationLabel).toBe(provided.resolveLocation);
    expect(provided.ensureLocations).toHaveBeenCalledTimes(1);
  });

  it('does not load names for a collapsed object panel or for a leaf panel', () => {
    const collapsed = value();
    renderWith(<PhotoCardPanel context="PROJECT" />, collapsed);
    expect(collapsed.ensureLocations).not.toHaveBeenCalled();

    const leaf = value({}, ['ROOM:r1']);
    renderWith(<PhotoCardPanel context="ROOM" targetId="r1" locationSegments={['Salon']} />, leaf);
    expect(leaf.ensureLocations).not.toHaveBeenCalled();
  });
});
