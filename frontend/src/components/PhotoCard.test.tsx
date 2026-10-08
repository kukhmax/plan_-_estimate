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

const COUNTS: PhotoCounts = {
  project: 1,
  rooms: { r1: 2 },
  surfaces: { s1: 3 },
  openings: { o1: 4 },
  room_totals: { r1: 2 + 3 + 4 }, // the room's own, its surface's and the surface's opening's
  inspections: {}, findings: {}, lineages: {}, questions: {}, works: {}, work_surfaces: {}, inspection_surfaces: {},
};

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
        <PhotoCardButton context="ROOM" targetId="r1" />
        <PhotoCardPanel context="ROOM" targetId="r1" />
      </>,
      null,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('PhotoCardButton', () => {
  it.each([
    ['ROOM', 'r1', 'Zdjęcia: 9'], // a room's button shows every photo of the room, surfaces and openings included
    ['SURFACE', 's1', 'Zdjęcia: 3'],
    ['OPENING', 'o1', 'Zdjęcia: 4'],
    ['ROOM', 'unknown', 'Zdjęcia: 0'],
  ] as const)('%s %s shows its count', (context, targetId, name) => {
    renderWith(<PhotoCardButton context={context} targetId={targetId} />, value());
    expect(screen.getByRole('button', { name })).toBeInTheDocument();
  });

  it('shows inspection evidence counts: the inspection, one of its questions, a finding through its lineage', () => {
    const evidence = value({
      counts: { ...COUNTS, inspections: { i1: 5 }, questions: { i1: { q1: 2 } }, findings: { f1: 1 }, lineages: { L: 4 } },
    });
    const view = renderWith(
      <>
        <PhotoCardButton context="INSPECTION" targetId="i1" />
        <PhotoCardButton context="INSPECTION" targetId="i1" questionId="q1" />
        <PhotoCardButton context="FINDING" targetId="f1" lineageId="L" />
      </>,
      evidence,
    );
    expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual(['Zdjęcia: 5', 'Zdjęcia: 2', 'Zdjęcia: 4']);
    view.unmount();
  });

  it('keeps question-level sections apart by key', () => {
    const provided = value({}, [photoKey('INSPECTION', 'i1', 'q1')]);
    renderWith(
      <>
        <PhotoCardButton context="INSPECTION" targetId="i1" questionId="q1" />
        <PhotoCardButton context="INSPECTION" targetId="i1" questionId="q2" />
        <PhotoCardButton context="INSPECTION" targetId="i1" />
      </>,
      provided,
    );
    const [q1, q2, header] = screen.getAllByRole('button');
    expect([q1, q2, header].map((b) => b.getAttribute('aria-expanded'))).toEqual(['true', 'false', 'false']);
    fireEvent.click(q2);
    expect(provided.toggle).toHaveBeenCalledWith('INSPECTION:i1:q2');
    fireEvent.click(header);
    expect(provided.toggle).toHaveBeenCalledWith('INSPECTION:i1');
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

  it('renders the bare button, so a card can place it in its own header line', () => {
    const { container } = renderWith(<PhotoCardButton context="SURFACE" targetId="s1" />, value());
    expect(container.firstElementChild?.tagName).toBe('BUTTON');
  });
});

describe('PhotoCardPanel', () => {
  it('mounts the section only while expanded (nothing is fetched while collapsed)', () => {
    renderWith(<PhotoCardPanel context="ROOM" targetId="r1" locationSegments={['Salon']} />, value());
    expect(screen.queryByTestId('photo-section')).toBeNull();
    expect(sectionProps).not.toHaveBeenCalled();
  });

  it('a surface panel gets its target, its room, the host names as a fixed location, the count callback — and uploading', () => {
    const provided = value({}, [photoKey('SURFACE', 's1')]);
    renderWith(<PhotoCardPanel context="SURFACE" targetId="s1" roomId="r1" locationSegments={['Salon', 'Ściana 1']} />, provided);
    expect(sectionProps).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: 'p1',
        context: 'SURFACE',
        targetId: 's1',
        roomId: 'r1',
        allowUpload: true,
        locationLabel: 'Salon → Ściana 1',
        onCountAdjust: provided.adjust,
      }),
    );
  });

  it.each([
    ['PROJECT', undefined],
    ['ROOM', 'r1'],
  ] as const)('the %s panel is an aggregated list: no uploading, every photo resolved through the context', (context, targetId) => {
    const provided = value({}, [photoKey(context, targetId)]);
    renderWith(<PhotoCardPanel context={context} targetId={targetId} locationSegments={['ignored']} />, provided);
    expect(sectionProps.mock.calls[0][0]).toMatchObject({ context, targetId, allowUpload: false });
    expect(sectionProps.mock.calls[0][0].locationLabel).toBe(provided.resolveLocation);
  });

  it('an inspection / question / finding panel offers uploading and passes its identity and caption resolver on', () => {
    const resolver = vi.fn(() => 'Pytanie');
    const provided = value({}, [photoKey('INSPECTION', 'i1'), photoKey('INSPECTION', 'i1', 'q1'), photoKey('FINDING', 'f1')]);
    renderWith(
      <>
        <PhotoCardPanel context="INSPECTION" targetId="i1" locationSegments={['Oględziny']} locationLabel={resolver} />
        <PhotoCardPanel context="INSPECTION" targetId="i1" questionId="q1" locationSegments={['Oględziny', 'Pytanie 1']} />
        <PhotoCardPanel context="FINDING" targetId="f1" lineageId="L" locationSegments={['Oględziny', 'Pęknięcie']} />
      </>,
      provided,
    );
    const [header, question, finding] = sectionProps.mock.calls.map((call) => call[0]);
    expect(header).toMatchObject({ context: 'INSPECTION', targetId: 'i1', allowUpload: true, locationLabel: resolver });
    expect(question).toMatchObject({ context: 'INSPECTION', targetId: 'i1', questionId: 'q1', allowUpload: true, locationLabel: 'Oględziny → Pytanie 1' });
    expect(finding).toMatchObject({ context: 'FINDING', targetId: 'f1', lineageId: 'L', allowUpload: true, locationLabel: 'Oględziny → Pęknięcie' });
    for (const props of [header, question, finding]) expect(props.onCountAdjust).toBe(provided.adjust);
  });

  it('an inspection panel does not load the project names (it is not an aggregated list)', () => {
    const provided = value({}, [photoKey('INSPECTION', 'i1')]);
    renderWith(<PhotoCardPanel context="INSPECTION" targetId="i1" locationSegments={['x']} />, provided);
    expect(provided.ensureLocations).not.toHaveBeenCalled();
  });

  it('an opening panel (legacy photos only) never offers uploading', () => {
    renderWith(<PhotoCardPanel context="OPENING" targetId="o1" locationSegments={['x']} />, value({}, ['OPENING:o1']));
    expect(sectionProps.mock.calls[0][0]).toMatchObject({ context: 'OPENING', allowUpload: false });
  });

  it('writes a dash for a host name that is missing', () => {
    renderWith(<PhotoCardPanel context="SURFACE" targetId="s1" locationSegments={[undefined, 'Ściana 1']} />, value({}, ['SURFACE:s1']));
    expect(sectionProps.mock.calls[0][0].locationLabel).toBe('— → Ściana 1');
  });

  it('an aggregated panel loads the names when it opens: the whole object, or just its own room', () => {
    const object = value({}, [photoKey('PROJECT')]);
    renderWith(<PhotoCardPanel context="PROJECT" />, object);
    expect(object.ensureLocations).toHaveBeenCalledTimes(1);
    expect(object.ensureLocations).toHaveBeenCalledWith(undefined);

    const room = value({}, [photoKey('ROOM', 'r1')]);
    renderWith(<PhotoCardPanel context="ROOM" targetId="r1" />, room);
    expect(room.ensureLocations).toHaveBeenCalledTimes(1);
    expect(room.ensureLocations).toHaveBeenCalledWith('r1');
  });

  it('does not load names for a collapsed panel or for a surface panel', () => {
    const collapsed = value();
    renderWith(<PhotoCardPanel context="PROJECT" />, collapsed);
    renderWith(<PhotoCardPanel context="ROOM" targetId="r1" />, collapsed);
    expect(collapsed.ensureLocations).not.toHaveBeenCalled();

    const surface = value({}, ['SURFACE:s1']);
    renderWith(<PhotoCardPanel context="SURFACE" targetId="s1" locationSegments={['Salon']} />, surface);
    expect(surface.ensureLocations).not.toHaveBeenCalled();
  });
});

describe('execution evidence (14H)', () => {
  const WORK_COUNTS: PhotoCounts = { ...COUNTS, works: { k1: 2, k2: 1 }, work_surfaces: { s1: 5 } };

  it('a work button counts that work, a surface-level one every execution photo, never the site photos', () => {
    renderWith(
      <>
        <PhotoCardButton context="WORK" targetId="s1" occurrenceKey="k1" />
        <PhotoCardButton context="WORK" targetId="s1" occurrenceKey="k2" />
        <PhotoCardButton context="WORK" targetId="s1" occurrenceKey="nobody" />
        <PhotoCardButton context="WORK" targetId="s1" />
      </>,
      value({ counts: WORK_COUNTS }),
    );
    expect(screen.getByRole('button', { name: 'Zdjęcia: 2' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zdjęcia: 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zdjęcia: 0' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zdjęcia: 5' })).toBeInTheDocument();
  });

  it('toggles under a key of its own, apart from the surface\'s site section and from other works', () => {
    const toggle = vi.fn();
    renderWith(<PhotoCardButton context="WORK" targetId="s1" occurrenceKey="k1" />, value({ counts: WORK_COUNTS, toggle }));
    fireEvent.click(screen.getByRole('button', { name: 'Zdjęcia: 2' }));
    expect(toggle).toHaveBeenCalledWith(photoKey('WORK', 's1', 'k1'));
    expect(photoKey('WORK', 's1', 'k1')).not.toBe(photoKey('SURFACE', 's1'));
    expect(photoKey('WORK', 's1', 'k1')).not.toBe(photoKey('WORK', 's1', 'k2'));
  });

  it('the panel mounts one section for the work with the suggested category and uploading allowed', () => {
    renderWith(
      <PhotoCardPanel context="WORK" targetId="s1" occurrenceKey="k1" defaultCategory="BEFORE" locationSegments={['Ściana A', 'Gładź']} />,
      value({ counts: WORK_COUNTS }, [photoKey('WORK', 's1', 'k1')]),
    );
    expect(sectionProps).toHaveBeenLastCalledWith(
      expect.objectContaining({
        context: 'WORK',
        targetId: 's1',
        occurrenceKey: 'k1',
        defaultCategory: 'BEFORE',
        allowUpload: true,
        projectId: 'p1',
      }),
    );
  });

  it('stays closed while another work of the same surface is the open one', () => {
    renderWith(
      <PhotoCardPanel context="WORK" targetId="s1" occurrenceKey="k1" locationSegments={['Ściana A']} />,
      value({ counts: WORK_COUNTS }, [photoKey('WORK', 's1', 'k2')]),
    );
    expect(screen.queryByTestId('photo-section')).toBeNull();
  });

  it('the list of detached evidence can be made view-only and keeps its exclusion list', () => {
    const exclude = new Set(['k1', 'k2']);
    renderWith(
      <PhotoCardPanel context="WORK" targetId="s1" excludeKeys={exclude} allowUpload={false} locationSegments={['Ściana A']} />,
      value({ counts: WORK_COUNTS }, [photoKey('WORK', 's1')]),
    );
    expect(sectionProps).toHaveBeenLastCalledWith(expect.objectContaining({ context: 'WORK', allowUpload: false, excludeKeys: exclude }));
  });
});
