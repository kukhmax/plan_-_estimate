import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { PhotoAttachmentRead, PhotoContext, PhotoCounts } from '../types/photo';
import { buildLocationPath } from '../utils/photoCaption';
import {
  EMPTY_LOCATIONS,
  PhotoLocationData,
  loadPhotoLocations,
  resolveLocationSegments,
} from '../utils/photoLocations';
import { targetIdOf } from '../utils/photoTarget';
import { PhotoBackContext, PhotoBackRegistry } from './PhotoBackContext';
import { useI18n } from './useI18n';
import { subscribePhotoUploadDone, subscribePhotoUploadRefetch } from './usePhotoUploadQueue';
import { usePhotoCounts } from './usePhotoCounts';

// Everything the cards of ONE open object share about photos (contract §9, §3, §8):
//  - the counts of the badges (one request per object, optimistic corrections, refetch when a section expands);
//  - which sections are expanded (so the corner button and its panel need no shared parent);
//  - the count of every FINISHED upload — counted here, once, whether or not its section is still open;
//  - location names for the project-wide list; - the BackButton registry for the viewer.
// Without a provider (existing tests, other screens) the photo buttons and panels render nothing.

export interface ProjectPhotosValue {
  projectId: string;
  counts: PhotoCounts;
  isExpanded: (key: string) => boolean;
  toggle: (key: string) => void;
  adjust: (context: PhotoContext, targetId: string | undefined, delta: number) => void;
  /** Location text of an attachment for the project-wide list (names resolved lazily; a dash when unknown). */
  resolveLocation: (attachment: PhotoAttachmentRead) => string;
  /** Start (re)loading the names; called when the project-wide section opens. */
  ensureLocations: () => void;
}

export const ProjectPhotosContext = createContext<ProjectPhotosValue | null>(null);

export function useProjectPhotos(): ProjectPhotosValue | null {
  return useContext(ProjectPhotosContext);
}

export function photoKey(context: PhotoContext, targetId?: string): string {
  return `${context}:${targetId ?? ''}`;
}

interface ProjectPhotosProviderProps {
  /** The open object; null while the project list is shown (nothing is loaded then). */
  projectId: string | null;
  backRegistry: PhotoBackRegistry;
  children: ReactNode;
}

export function ProjectPhotosProvider({ projectId, backRegistry, children }: ProjectPhotosProviderProps) {
  const { t } = useI18n();
  const { counts, refresh, adjust } = usePhotoCounts(projectId);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [locations, setLocations] = useState<PhotoLocationData>(EMPTY_LOCATIONS);
  const locationToken = useRef(0);
  const countsRef = useRef(counts);
  useEffect(() => {
    countsRef.current = counts;
  }, [counts]);

  // A different object: collapse everything and forget its names.
  useEffect(() => {
    setExpanded(new Set());
    setLocations(EMPTY_LOCATIONS);
    locationToken.current += 1;
  }, [projectId]);

  // Upload completions of this object are counted HERE (not by a section): the upload continues after its section is
  // collapsed and several sections can be open at once, so a section-level count would be missed or doubled.
  useEffect(() => {
    if (!projectId) return;
    const offDone = subscribePhotoUploadDone((item) => {
      if (item.target.projectId === projectId) adjust(item.target.context, targetIdOf(item.target), 1);
    });
    const offRefetch = subscribePhotoUploadRefetch((what, item) => {
      if (what === 'parent' && item.target.projectId === projectId) void refresh();
    });
    return () => {
      offDone();
      offRefetch();
    };
  }, [projectId, adjust, refresh]);

  const isExpanded = useCallback((key: string) => expanded.has(key), [expanded]);
  const toggle = useCallback(
    (key: string) => {
      const opening = !expanded.has(key);
      setExpanded((current) => {
        const next = new Set(current);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
      if (opening) void refresh(); // counts are refetched whenever a section expands (contract §9)
    },
    [expanded, refresh],
  );

  const ensureLocations = useCallback(() => {
    if (!projectId) return;
    const token = ++locationToken.current;
    void loadPhotoLocations(projectId, countsRef.current).then((data) => {
      if (token === locationToken.current) setLocations(data);
    });
  }, [projectId]);

  const labels = useMemo(
    () => ({
      wall: t.surfaces.wall,
      floor: t.surfaces.floor,
      ceiling: t.surfaces.ceiling,
      door: t.openings.door,
      window: t.openings.window,
      other: t.openings.other,
    }),
    [t],
  );

  const resolveLocation = useCallback(
    (attachment: PhotoAttachmentRead) =>
      buildLocationPath(resolveLocationSegments(attachment, locations, labels), t.photos.caption),
    [locations, labels, t],
  );

  const value = useMemo<ProjectPhotosValue | null>(
    () =>
      projectId
        ? { projectId, counts, isExpanded, toggle, adjust, resolveLocation, ensureLocations }
        : null,
    [projectId, counts, isExpanded, toggle, adjust, resolveLocation, ensureLocations],
  );

  return (
    <PhotoBackContext.Provider value={backRegistry}>
      <ProjectPhotosContext.Provider value={value}>{children}</ProjectPhotosContext.Provider>
    </PhotoBackContext.Provider>
  );
}
