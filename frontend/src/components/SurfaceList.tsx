import { INSPECT_BUTTON_WITH_BADGE, InspectionPhotoBadge } from './ExecutionPhotoBadge';
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/http';
import { fetchOpenings } from '../api/openings';
import {
  archiveSurface,
  createSurface,
  duplicateMergedSurface,
  fetchSurfaces,
  generateWalls,
  mergeSurfaces,
  restoreSurface,
  unmergeSurface,
  updateSurface,
  updateSurfacePart,
} from '../api/surfaces';
import { useI18n } from '../hooks/useI18n';
import { OpeningType, OpeningTypeValue } from '../types/opening';
import {
  SurfaceCreatePayload,
  SurfaceType,
  SurfaceTypeValue,
  SurfaceUpdatePayload,
} from '../types/surface';
import { sumDecimalStrings } from '../utils/decimalArithmetic';
import { formatMetric } from '../utils/format';
import { surfaceCardTint } from '../utils/surfaceColorTint';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { PhotoCardButton, PhotoCardPanel } from './PhotoCard';
import { surfaceTypeTint } from '../utils/surfaceTypeTint';
import { formatOpeningDimension, summarizeOpenings } from '../utils/openingSummary';
import { OpeningList } from './OpeningList';
import { SurfaceExecutionView } from './SurfaceExecutionView';
import { SurfaceWorkPlanEditor } from './SurfaceWorkPlanEditor';
import { DimensionInput } from './DimensionInput';
import { Ico } from './Ico';
import { PlanExecutionTabs } from './PlanExecutionTabs';
import { PendingMark } from './PendingMark';
import { SurfaceDimensions } from './SurfaceDimensions';
import { SurfaceRowButton } from './SurfaceRowButton';
import { previewArea } from '../offline/preview';

/** Header type-pill: a single neutral style legible against any card tint
 * (WALL cards no longer share one fixed background — see surfaceColorTint). */
const TYPE_BADGE_CLASS = 'pe-surface text-slate-700';

interface SurfaceListProps {
  projectId: string;
  roomId: string;
  /** Room name for the photo caption path (Stage 14E.5); optional. */
  roomName?: string;
  roomHeight?: string | number | null;
  hasRoomDimensions?: boolean;
  /** Changes whenever the room size is corrected, so the cards re-read the recalculated planes. */
  dimensionsKey?: string;
  wallMode?: WallInputMode;
  /** Open every wall card on the first load (a collapsed row is the default). */
  initiallyOpen?: boolean;
  onMeasurementChanged?: () => void;
  /** Open the inspection checklist for a wall surface (Stage 6C entry point). */
  onInspectSurface?: (surfaceId: string, surfaceName: string) => void;
}

export type WallInputMode = 'RECTANGLE' | 'CUSTOM';

interface SurfaceFormState {
  name: string;
  surface_type: SurfaceTypeValue;
  description: string;
  width: string;
  height: string;
}

interface CustomWallFormState {
  width: string;
  height: string;
  differentHeight: boolean;
}

interface PendingQuickOpening {
  surfaceId: string;
  type: OpeningTypeValue;
  key: number;
}

const EMPTY_FORM: SurfaceFormState = {
  name: '',
  surface_type: 'WALL',
  description: '',
  width: '',
  height: '',
};


export function SurfaceList({
  projectId,
  roomId,
  roomName,
  roomHeight,
  hasRoomDimensions = false,
  dimensionsKey,
  wallMode,
  initiallyOpen = false,
  onMeasurementChanged,
  onInspectSurface,
}: SurfaceListProps) {
  const { t } = useI18n();
  const surfaceDisplayLabels = {
    wall: t.surfaces.wall,
    floor: t.surfaces.floor,
    ceiling: t.surfaces.ceiling,
  };
  const [surfaces, setSurfaces] = useState<SurfaceType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [form, setForm] = useState<SurfaceFormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [expandedOpenings, setExpandedOpenings] = useState<Record<string, boolean>>({});
  /** Per-card Opcje progressive disclosure — UI state only, never persisted. */
  const [expandedOptions, setExpandedOptions] = useState<Record<string, boolean>>({});
  /** Which wall cards are open (the others are one-line rows). `null` while nothing was opened or closed: then `initiallyOpen` decides. */
  const [openCards, setOpenCards] = useState<Record<string, boolean>>({});
  /** Usability U-7: which wall cards show their area calculation (gross, openings, reveals); the net area alone is the default. */
  const [expandedAreas, setExpandedAreas] = useState<Record<string, boolean>>({});
  const toggleAreaDetails = (surfaceId: string) => setExpandedAreas((current) => ({ ...current, [surfaceId]: !current[surfaceId] }));
  const [activeWorkPlanSurfaceId, setActiveWorkPlanSurfaceId] = useState<string | null>(null);
  // Stage 13H.5: Realizacja (execution) is a separate view from the plan
  // editor; at most one of the two is open, so neither shows stale data.
  const [activeExecutionSurfaceId, setActiveExecutionSurfaceId] = useState<string | null>(null);
  const effectiveWallMode = wallMode ?? 'RECTANGLE';
  const [generating, setGenerating] = useState(false);
  /** null = not known yet (CTA hidden until known). */
  const [roomHasWalls, setRoomHasWalls] = useState<boolean | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [pendingQuickOpening, setPendingQuickOpening] = useState<PendingQuickOpening | null>(null);
  const quickActionKeyRef = useRef(0);
  // Stage 10G.4 — active (non-archived) openings per WALL surface, fetched
  // eagerly (read-only, existing endpoint) so the always-visible calculation
  // panel can explain the deduction and show the reveal aggregate without
  // requiring the owner to expand "Otwory" first. Independent from
  // OpeningList's own lazy fetch on expand — this is a display-only summary.
  const [wallOpeningsById, setWallOpeningsById] = useState<Record<string, OpeningType[]>>({});

  const roomHeightNum =
    roomHeight !== null && roomHeight !== undefined ? Number(roomHeight) : NaN;
  const hasRoomHeight = !Number.isNaN(roomHeightNum) && roomHeightNum > 0;
  const roomHeightStr = hasRoomHeight ? String(roomHeightNum) : '';

  const [customWall, setCustomWall] = useState<CustomWallFormState>({
    width: '',
    height: roomHeightStr,
    differentHeight: false,
  });

  const activeWallCount = surfaces.filter(
    (s) => s.surface_type === 'WALL' && !s.is_archived,
  ).length;
  const nextWallNumber = activeWallCount + 1;
  const nextWallPosition = surfaces.reduce(
    (max, s) => (typeof s.position === 'number' && s.position > max ? s.position : max),
    -1,
  ) + 1;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSurfaces(projectId, roomId, includeArchived);
      setSurfaces(data.items);
      // Stage 13F-PRE: the 4-wall generation CTA is offered only when the
      // room has no WALL surface at all -- archived ones included, because
      // the backend would create a second set next to archived walls.
      let hasWalls = data.items.some((s) => s.surface_type === 'WALL');
      if (!hasWalls && !includeArchived) {
        try {
          const all = await fetchSurfaces(projectId, roomId, true);
          hasWalls = all.items.some((s) => s.surface_type === 'WALL');
        } catch {
          hasWalls = true; // unknown -> never invite a possible duplicate set
        }
      }
      setRoomHasWalls(hasWalls);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.surfaces.error);
    } finally {
      setLoading(false);
    }
  }, [includeArchived, projectId, roomId, dimensionsKey, t.surfaces.error]);

  useEffect(() => {
    void load();
  }, [load]);

  // Stage 10G.4 — fetch active openings for every measured WALL so the
  // deduction/reveal summary rows have real data to describe. Best-effort
  // per surface: one wall's fetch failing never blocks the others or the
  // surface list itself (the calculation panel simply falls back to the
  // plain, context-free deduction row for that wall).
  useEffect(() => {
    let cancelled = false;
    const walls = surfaces.filter(
      (s) => s.surface_type === 'WALL' && !s.is_archived &&
        s.width !== null && s.width !== undefined &&
        s.height !== null && s.height !== undefined,
    );
    void Promise.all(
      walls.map(async (wall) => {
        try {
          const resp = await fetchOpenings(projectId, roomId, wall.id);
          return [wall.id, resp.items] as const;
        } catch {
          return [wall.id, null] as const;
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      setWallOpeningsById((current) => {
        const next = { ...current };
        for (const [id, items] of results) {
          if (items !== null) next[id] = items;
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [surfaces, projectId, roomId]);

  const toggleOptions = (surfaceId: string) => {
    setExpandedOptions((current) => ({
      ...current,
      [surfaceId]: !current[surfaceId],
    }));
  };

  const isCardOpen = (surfaceId: string) => openCards[surfaceId] ?? initiallyOpen;
  const toggleCard = (surfaceId: string) => {
    setOpenCards((current) => ({ ...current, [surfaceId]: !(current[surfaceId] ?? initiallyOpen) }));
  };

  const toggleWorkPlan = (surfaceId: string) => {
    setActiveExecutionSurfaceId(null);
    setActiveWorkPlanSurfaceId((current) => current === surfaceId ? null : surfaceId);
  };

  const toggleExecution = (surfaceId: string) => {
    setActiveWorkPlanSurfaceId(null);
    setActiveExecutionSurfaceId((current) => current === surfaceId ? null : surfaceId);
  };

  const openWorkPlanFromExecution = (surfaceId: string) => {
    setActiveExecutionSurfaceId(null);
    setActiveWorkPlanSurfaceId(surfaceId);
  };

  const toggleOpenings = (surfaceId: string) => {
    setExpandedOpenings((current) => ({
      ...current,
      [surfaceId]: !current[surfaceId],
    }));
    if (pendingQuickOpening?.surfaceId === surfaceId) {
      setPendingQuickOpening(null);
    }
  };

  const quickAddOpening = (surfaceId: string, type: OpeningTypeValue) => {
    setExpandedOpenings((current) => ({ ...current, [surfaceId]: true }));
    setPendingQuickOpening({
      surfaceId,
      type,
      key: ++quickActionKeyRef.current,
    });
  };

  const handleOpeningChanged = () => {
    void load();
    onMeasurementChanged?.();
  };

  const handleGenerateWalls = async () => {
    setGenerating(true);
    setGenerateError(null);
    setSuccess(null);
    try {
      await generateWalls(projectId, roomId);
      setSuccess(t.surfaces.walls_generated);
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : t.surfaces.error);
    } finally {
      setGenerating(false);
    }
  };

  const handleCustomWallSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);

    const widthVal = parseFloat(customWall.width.trim());
    const heightVal = customWall.differentHeight
      ? parseFloat(customWall.height.trim())
      : (hasRoomHeight ? roomHeightNum : NaN);

    if (Number.isNaN(widthVal) || widthVal <= 0 ||
        Number.isNaN(heightVal) || heightVal <= 0) {
      setFormError(t.surfaces.custom_wall_invalid);
      setSaving(false);
      return;
    }

    const payload: SurfaceCreatePayload = {
      name: `${t.surfaces.wall} ${nextWallNumber}`,
      surface_type: 'WALL',
      position: nextWallPosition,
      width: widthVal,
      height: heightVal,
      description: null,
    };

    try {
      await createSurface(projectId, roomId, payload);
      setSuccess(t.surfaces.created);
      setCustomWall({ width: '', height: roomHeightStr, differentHeight: false });
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t.surfaces.error);
    } finally {
      setSaving(false);
    }
  };

  /** The same wall once more (an irregular room has several of one size): next number, next position, same width and height. */
  const handleDuplicateWall = async (surface: SurfaceType) => {
    setError(null);
    setSuccess(null);
    try {
      const created = await createSurface(projectId, roomId, {
        name: `${t.surfaces.wall} ${nextWallNumber}`,
        surface_type: 'WALL',
        position: nextWallPosition,
        width: Number(surface.width),
        height: Number(surface.height),
        description: null,
      });
      setSuccess(t.surfaces.duplicated);
      setOpenCards((current) => ({ ...current, [created.id]: true }));
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.surfaces.error);
    }
  };

  // --- Merged walls (backlog "Объединить стены") -----------------------------------------------------------------------------------------
  /** Selection mode: the walls are marked one by one (the order is kept: the first stays and keeps the plan). */
  const [selecting, setSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [mergeConfirm, setMergeConfirm] = useState(false);
  const [mergeBusy, setMergeBusy] = useState(false);
  const [unmergeConfirmId, setUnmergeConfirmId] = useState<string | null>(null);

  const mergeErrorText = (err: unknown): string => {
    const code = err instanceof ApiError ? err.code : undefined;
    const known = code ? (t.surfaces.merge_errors as Record<string, string>)[code] : undefined;
    return known ?? (err instanceof Error ? err.message : t.surfaces.error);
  };
  const startSelecting = (firstId?: string) => {
    setError(null);
    setSuccess(null);
    setMergeConfirm(false);
    setSelecting(true);
    setSelectedIds(firstId ? [firstId] : []);
  };
  const stopSelecting = () => {
    setSelecting(false);
    setSelectedIds([]);
    setMergeConfirm(false);
  };
  const toggleSelected = (surfaceId: string) => {
    setMergeConfirm(false);
    setSelectedIds((current) => (current.includes(surfaceId) ? current.filter((id) => id !== surfaceId) : [...current, surfaceId]));
  };
  const handleMerge = async () => {
    setMergeBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const merged = await mergeSurfaces(projectId, roomId, selectedIds);
      stopSelecting();
      setSuccess(t.surfaces.merged_done);
      setOpenCards((current) => ({ ...current, [merged.id]: true }));
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setError(mergeErrorText(err));
      setMergeConfirm(false);
    } finally {
      setMergeBusy(false);
    }
  };
  const handleUnmerge = async (surfaceId: string) => {
    setMergeBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await unmergeSurface(projectId, roomId, surfaceId);
      setUnmergeConfirmId(null);
      setSuccess(t.surfaces.unmerged_done);
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setError(mergeErrorText(err));
      setUnmergeConfirmId(null);
    } finally {
      setMergeBusy(false);
    }
  };
  const savePartSize = async (surfaceId: string, partId: string, width: number, height: number) => {
    setSuccess(null);
    try {
      await updateSurfacePart(projectId, roomId, surfaceId, partId, { width, height });
    } catch (err) {
      throw new Error(mergeErrorText(err)); // SurfaceDimensions shows the message under its fields
    }
    setSuccess(t.surfaces.dimensions_saved);
    await load();
    onMeasurementChanged?.();
  };

  /** A merged wall once more (an irregular room has several alike): a new merged wall with the same parts, the next number and position. */
  const handleDuplicateMerged = async (surface: SurfaceType) => {
    setError(null);
    setSuccess(null);
    setMergeBusy(true);
    try {
      const created = await duplicateMergedSurface(projectId, roomId, surface.id, {
        name: `${t.surfaces.wall} ${nextWallNumber}`,
        position: nextWallPosition,
      });
      setSuccess(t.surfaces.duplicated);
      setOpenCards((current) => ({ ...current, [created.id]: true }));
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setError(mergeErrorText(err));
    } finally {
      setMergeBusy(false);
    }
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const startEdit = (surface: SurfaceType) => {
    setSuccess(null);
    setEditingId(surface.id);
    setForm({
      name: surface.name,
      surface_type: surface.surface_type,
      description: surface.description ?? '',
      width: surface.width !== null && surface.width !== undefined ? String(surface.width) : '',
      height: surface.height !== null && surface.height !== undefined ? String(surface.height) : '',
    });
    setFormError(null);
    setShowForm(true);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);

    const widthVal = form.width.trim() ? parseFloat(form.width.trim()) : null;
    const heightVal = form.height.trim() ? parseFloat(form.height.trim()) : null;

    if (widthVal !== null && (Number.isNaN(widthVal) || widthVal <= 0)) {
      setFormError(t.surfaces.error);
      setSaving(false);
      return;
    }
    if (heightVal !== null && (Number.isNaN(heightVal) || heightVal <= 0)) {
      setFormError(t.surfaces.error);
      setSaving(false);
      return;
    }

    const payload: SurfaceCreatePayload = {
      name: form.name.trim(),
      surface_type: form.surface_type,
      description: form.description.trim() || null,
      width: widthVal,
      height: heightVal,
    };

    try {
      if (editingId) {
        const updatePayload: SurfaceUpdatePayload = {
          name: payload.name,
          surface_type: payload.surface_type,
          description: payload.description,
          width: payload.width,
          height: payload.height,
        };
        await updateSurface(projectId, roomId, editingId, updatePayload);
        setSuccess(t.surfaces.updated);
      } else {
        await createSurface(projectId, roomId, payload);
        setSuccess(t.surfaces.created);
      }
      closeForm();
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t.surfaces.error);
    } finally {
      setSaving(false);
    }
  };

  const saveDimensions = async (surfaceId: string, width: number, height: number) => {
    setSuccess(null);
    await updateSurface(projectId, roomId, surfaceId, { width, height });
    setSuccess(t.surfaces.dimensions_saved);
    await load();
    onMeasurementChanged?.();
  };

  const changeArchiveState = async (surface: SurfaceType) => {
    setError(null);
    setSuccess(null);
    try {
      if (surface.is_archived) {
        await restoreSurface(projectId, roomId, surface.id);
        setSuccess(t.surfaces.restored);
      } else {
        await archiveSurface(projectId, roomId, surface.id);
        setSuccess(t.surfaces.archived);
      }
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.surfaces.error);
    }
  };

  const typeLabel = (surfaceType: SurfaceTypeValue) => {
    const labels: Record<SurfaceTypeValue, string> = {
      WALL: t.surfaces.wall,
      CEILING: t.surfaces.ceiling,
      FLOOR: t.surfaces.floor,
      OTHER: t.surfaces.other,
    };
    return labels[surfaceType];
  };

  // AreaSegmentList is the sole FLOOR/CEILING representation; full state still drives identity and counts.
  const visibleSurfaces = surfaces.filter(
    (s) => s.surface_type !== 'FLOOR' && s.surface_type !== 'CEILING',
  );

  /** Walls that can be joined: active, with a size, not merged yet. */
  const isMergeable = (surface: SurfaceType) =>
    surface.surface_type === 'WALL' && !surface.is_archived && surface.width != null && surface.height != null && !(surface.parts && surface.parts.length > 0);
  const mergeableWalls = visibleSurfaces.filter(isMergeable);
  const nameOf = (surfaceId: string | null | undefined) => {
    const found = surfaces.find((candidate) => candidate.id === surfaceId);
    return found ? getSurfaceDisplayName(found, surfaceDisplayLabels) : '';
  };

  const openingTypeWord = (type: OpeningTypeValue): string => {
    if (type === 'WINDOW') return t.surfaces.deduction_type_window;
    if (type === 'DOOR') return t.surfaces.deduction_type_door;
    return t.surfaces.deduction_type_other;
  };

  // Explains WHAT the existing backend-derived deduction_area is subtracting
  // — never recomputes it. Uses only already-fetched, active (non-archived)
  // Opening rows; the numeric value on the row always stays surface.deduction_area.
  const describeDeductionContext = (openings: OpeningType[] | undefined): string | null => {
    if (!openings || openings.length === 0) return null;
    if (openings.length === 1) {
      const o = openings[0];
      return `${openingTypeWord(o.opening_type)} ${formatMetric(o.width)} × ${formatMetric(o.height)}`;
    }
    const counts = new Map<OpeningTypeValue, number>();
    for (const o of openings) counts.set(o.opening_type, (counts.get(o.opening_type) ?? 0) + 1);
    const types = Array.from(counts.keys());
    if (types.length === 1) {
      return `${openings.length} × ${openingTypeWord(types[0])}`;
    }
    // Many openings, mixed types: a compact count beats a long join list.
    if (openings.length > 6) {
      return `${openings.length} ${t.surfaces.deduction_openings_generic}`;
    }
    return types.map((ty) => openingTypeWord(ty)).join(' + ');
  };

  // Sums already-authoritative per-opening reveal totals for display only —
  // never recomputes reveal geometry. null when no reveal-enabled opening
  // exists on this wall (row is hidden entirely in that case).
  const describeRevealAggregate = (
    openings: OpeningType[] | undefined,
  ): { length: string; area: string } | null => {
    if (!openings) return null;
    const withReveal = openings.filter(
      (o) => o.reveal_enabled && o.reveal_total_length != null,
    );
    if (withReveal.length === 0) return null;
    return {
      length: sumDecimalStrings(withReveal.map((o) => String(o.reveal_total_length))),
      area: sumDecimalStrings(withReveal.map((o) => String(o.reveal_total_area ?? '0'))),
    };
  };

  return (
    <section aria-label="surfaces-section" className="w-full mt-5">
      <h3 className="text-lg font-bold text-[var(--tg-theme-text-color)] mb-3">{t.surfaces.walls_section_title}</h3>

      {effectiveWallMode === 'RECTANGLE' && hasRoomDimensions && roomHasWalls === false && (
        <div className="mb-3">
          <button
            type="button"
            aria-label="generate-walls"
            onClick={() => void handleGenerateWalls()}
            disabled={generating}
            className="w-full min-h-11 px-3 py-2 text-sm bg-emerald-600 text-white font-semibold rounded-xl hover:bg-emerald-700 transition disabled:opacity-60"
          >
            {generating ? t.common.saving : t.surfaces.generate_walls}
          </button>
          <p className="text-[11px] text-slate-400 mt-1.5">{t.surfaces.generate_hint}</p>
          {generateError && (
            <p role="alert" className="text-xs text-red-600 font-medium bg-red-50 border border-red-100 rounded-lg px-2.5 py-1.5 mt-2">
              {generateError}
            </p>
          )}
        </div>
      )}

      {effectiveWallMode === 'CUSTOM' && (
        <div
          aria-label="custom-wall-entry"
          className="pe-card rounded-2xl p-4 mb-3 shadow-sm"
        >
          <div className="flex items-center justify-between mb-1.5">
            <h4 className="text-sm font-semibold text-slate-900">{t.surfaces.custom_walls_title}</h4>
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">
              {t.surfaces.wall} {nextWallNumber}
            </span>
          </div>
          <p className="text-xs text-slate-500 mb-3">{t.surfaces.custom_walls_hint}</p>

          <form
            aria-label="custom-wall-form"
            onSubmit={handleCustomWallSubmit}
            className="space-y-2.5"
          >
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-slate-500 mb-1">{t.surfaces.width}</label>
                <DimensionInput
                  aria-label="custom-wall-width"
                  placeholder="200"
                  autoFocus
                  value={customWall.width}
                  onValueChange={(meters) => setCustomWall((cur) => ({ ...cur, width: meters }))}
                  className="w-full min-h-11 border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">{t.surfaces.height}</label>
                {customWall.differentHeight ? (
                  <DimensionInput
                    aria-label="custom-wall-height"
                    placeholder="270"
                    value={customWall.height}
                    onValueChange={(meters) => setCustomWall((cur) => ({ ...cur, height: meters }))}
                    className="w-full min-h-11 border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
                  />
                ) : (
                  <input
                    aria-label="custom-wall-height"
                    type="text"
                    readOnly
                    value={`${formatMetric(hasRoomHeight ? roomHeightNum : null)} ${t.common.unit_m}`}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm text-slate-500"
                  />
                )}
              </div>
            </div>

            <label className="flex items-center min-h-11 gap-1.5 text-xs text-slate-500 cursor-pointer">
              <input
                aria-label="custom-wall-different-height"
                type="checkbox"
                checked={customWall.differentHeight}
                onChange={(e) => setCustomWall((cur) => ({
                  ...cur,
                  differentHeight: e.target.checked,
                  height: e.target.checked ? cur.height || roomHeightStr : roomHeightStr,
                }))}
              />
              {t.surfaces.use_different_height}
            </label>

            {formError && <p role="alert" className="text-sm text-red-600 font-medium">{formError}</p>}

            <button
              type="submit"
              aria-label="add-custom-wall"
              disabled={saving}
              className="w-full min-h-11 px-3 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              {saving ? t.common.saving : t.surfaces.add_wall}
            </button>
          </form>
        </div>
      )}

      <label className="flex items-center gap-2 min-h-11 text-sm text-slate-600 mb-3 cursor-pointer">
        <input
          aria-label="show-archived-surfaces"
          type="checkbox"
          checked={includeArchived}
          onChange={(event) => setIncludeArchived(event.target.checked)}
        />
        {t.common.show_archived}
      </label>

      {effectiveWallMode === 'CUSTOM' && !selecting && !loading && mergeableWalls.length >= 2 && (
        <button
          type="button"
          aria-label="merge-walls-start"
          onClick={() => startSelecting()}
          className="mb-3 w-full min-h-11 px-3 py-2 text-sm rounded-xl border border-blue-200 bg-blue-50 text-blue-700 font-semibold hover:bg-blue-100 transition"
        >
          <Ico>🔗</Ico>{t.surfaces.merge_start}
        </button>
      )}
      {selecting && (
        <p aria-label="merge-hint" className="mb-3 text-xs text-slate-600 break-words">{t.surfaces.merge_hint}</p>
      )}

      {showForm && (
        <form
          aria-label="surface-form"
          onSubmit={handleSubmit}
          className="pe-card rounded-2xl p-4 mb-4 shadow-sm space-y-3"
        >
          <h4 className="font-semibold text-slate-900">
            {editingId ? t.surfaces.edit : t.surfaces.add}
          </h4>
          <input
            aria-label="surface-name"
            required
            maxLength={255}
            placeholder={t.surfaces.name}
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <select
            aria-label="surface-type"
            value={form.surface_type}
            onChange={(event) => setForm((current) => ({
              ...current,
              surface_type: event.target.value as SurfaceTypeValue,
            }))}
            className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            {(['WALL', 'CEILING', 'FLOOR', 'OTHER'] as const).map((value) => (
              <option key={value} value={value}>{typeLabel(value)}</option>
            ))}
          </select>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t.surfaces.width}</label>
              <DimensionInput
                aria-label="surface-width"
                placeholder="500"
                value={form.width}
                onValueChange={(meters) => setForm((current) => ({ ...current, width: meters }))}
                className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t.surfaces.height}</label>
              <DimensionInput
                aria-label="surface-height"
                placeholder="270"
                value={form.height}
                onValueChange={(meters) => setForm((current) => ({ ...current, height: meters }))}
                className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>

          <textarea
            aria-label="surface-description"
            maxLength={4096}
            placeholder={t.surfaces.description}
            value={form.description}
            onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-20"
          />
          {formError && <p role="alert" className="text-sm text-red-600 font-medium">{formError}</p>}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={closeForm}
              className="min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
            >
              <Ico>✖️</Ico>{t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="min-h-11 px-3 py-1 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              <Ico>💾</Ico>{saving ? t.common.saving : t.common.save}
            </button>
          </div>
        </form>
      )}

      {success && <p role="status" className="text-sm text-emerald-700 mb-3">{success}</p>}
      {loading && <p className="text-sm text-slate-500 text-center py-4">{t.surfaces.loading}</p>}
      {!loading && error && <p role="alert" className="text-sm text-red-600 text-center py-4">{error}</p>}
      {!loading && !error && visibleSurfaces.length === 0 && (
        <p aria-label="no-surfaces" className="text-sm text-slate-400 text-center py-6">
          {t.surfaces.empty}
        </p>
      )}
      {!loading && !error && visibleSurfaces.length > 0 && (
        <ul aria-label="surfaces-list" className="space-y-3">
          {visibleSurfaces.map((surface, _index, all) => {
            const hasDimensions = surface.width !== null && surface.width !== undefined &&
                                  surface.height !== null && surface.height !== undefined;
            const isWall = surface.surface_type === 'WALL';
            // a wall only the phone knows has no area from the server yet: its typed width × height is shown, marked "~" (Q5 (b))
            const waitingArea = surface._pending && surface.gross_area == null ? previewArea(surface.width, surface.height) : null;
            const isOpeningsOpen = !!expandedOpenings[surface.id];
            const isOptionsOpen = !!expandedOptions[surface.id];
            const isWorkPlanOpen = activeWorkPlanSurfaceId === surface.id;
            const isExecutionOpen = activeExecutionSurfaceId === surface.id;
            const displayName = getSurfaceDisplayName(surface, surfaceDisplayLabels);
            // WALL: deterministic per-surface-id hash tint (Stage 10G.2 helper,
            // extracted/reused — every wall gets its own stable color, never
            // shared across walls). Non-WALL (OTHER): stable type-only tint.
            const tint = isWall ? surfaceCardTint(surface.id) : surfaceTypeTint(surface.surface_type);
            const wallOpenings = wallOpeningsById[surface.id];
            const deductionContext = isWall ? describeDeductionContext(wallOpenings) : null;
            const revealAggregate = isWall ? describeRevealAggregate(wallOpenings) : null;
            // Compact read-only opening summary (active openings only).
            const openingSummary = isWall ? summarizeOpenings(wallOpenings) : [];
            const openingTypeLabel = (type: 'DOOR' | 'WINDOW' | 'OTHER') =>
              type === 'DOOR' ? t.openings.door : type === 'WINDOW' ? t.openings.window : t.openings.other;

            const partsCount = surface.parts?.length ?? 0;
            const selectedOrder = selectedIds.indexOf(surface.id) >= 0 ? selectedIds.indexOf(surface.id) + 1 : null;
            if (isWall && (selecting || !isCardOpen(surface.id))) {
              return (
                <li key={surface.id} aria-label={`surface-item-${surface.id}`}>
                  <SurfaceRowButton
                    partsLabel={partsCount > 0 ? String(partsCount) : null}
                    mergedLabel={surface.merged_into_id ? t.surfaces.merged_into.replace('{name}', nameOf(surface.merged_into_id)) : null}
                    selecting={selecting}
                    selectedOrder={selectedOrder}
                    disabled={selecting && !isMergeable(surface)}
                    stayLabel={t.surfaces.merge_first_stays}
                    onLongPress={effectiveWallMode === 'CUSTOM' && isMergeable(surface) && mergeableWalls.length >= 2 ? () => startSelecting(surface.id) : undefined}
                    surfaceId={surface.id}
                    name={displayName}
                    typeLabel={typeLabel(surface.surface_type)}
                    area={waitingArea ? `~${waitingArea} ${t.common.unit_m2}` : hasDimensions ? `${formatMetric(surface.net_area ?? surface.gross_area)} ${t.common.unit_m2}` : '—'}
                    archivedLabel={surface.is_archived ? t.common.archived_badge : null}
                    workCount={surface.planned_work_count}
                    pending={surface._pending}
                    className={`${tint.bg} border ${tint.border} ${tint.extra} rounded-xl px-3 py-1.5 min-h-11 w-full flex items-center gap-2 shadow-sm`}
                    onOpen={() => (selecting ? toggleSelected(surface.id) : toggleCard(surface.id))}
                  />
                </li>
              );
            }

            return (
              <li
                key={surface.id}
                aria-label={`surface-item-${surface.id}`}
                className={`${tint.bg} border ${tint.border} ${tint.extra} rounded-2xl p-3 shadow-sm space-y-2`}
              >
                {/* Header: name + badges (left) and compact Opcje (upper-right). */}
                <div className="flex items-start justify-between gap-2">
                  {(() => {
                    const headerContent = (
                      <>
                        {isWall && <span aria-hidden="true" className="text-slate-500">▴</span>}
                        <span className="font-semibold text-slate-900 text-sm min-w-0 break-words">{displayName}</span>
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_BADGE_CLASS}`}>
                          {typeLabel(surface.surface_type)}
                        </span>
                        {surface.is_archived && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                            {t.common.archived_badge}
                          </span>
                        )}
                        <PendingMark record={surface} id={surface.id} />
                      </>
                    );
                    // a wall card folds back into its one-line row by a tap on its name
                    return isWall ? (
                      <button
                        type="button"
                        aria-label={`card-collapse-${surface.id}`}
                        aria-expanded={true}
                        onClick={() => toggleCard(surface.id)}
                        className="min-w-0 flex-1 min-h-11 flex items-center gap-2 flex-wrap text-left"
                      >
                        {headerContent}
                      </button>
                    ) : (
                      <div className="min-w-0 flex-1 flex items-center gap-2 flex-wrap">{headerContent}</div>
                    );
                  })()}
                  {/* Stage 14E.7: the compact photo button sits in the header, left of Opcje (no row of its own);
                      nothing without a project context. */}
                  <PhotoCardButton context="SURFACE" targetId={surface.id} />
                  {/* Progressive disclosure: Opcje reveals the card's action grid. */}
                  <button
                    type="button"
                    aria-label={`options-toggle-${surface.id}`}
                    aria-expanded={isOptionsOpen}
                    onClick={() => toggleOptions(surface.id)}
                    className="shrink-0 max-w-[40%] min-h-11 px-3 py-1 text-sm leading-tight break-words rounded-xl bg-slate-100 text-slate-800 font-semibold hover:bg-slate-200 transition"
                  >
                    <Ico>{isOptionsOpen ? '🔼' : '⚙️'}</Ico>
                    {isWall
                      ? (isOptionsOpen ? t.surfaces.hide_openings_and_options : t.surfaces.openings_and_options)
                      : (isOptionsOpen ? t.surfaces.hide_options : t.surfaces.options)}
                  </button>
                </div>

                <PhotoCardPanel context="SURFACE" targetId={surface.id} roomId={roomId} locationSegments={[roomName, displayName]} />

                {/* The inspection is a main action of a wall: it sits right under Opcje, not inside it (owner, Stage 18G). */}
                {isWall && onInspectSurface && (
                  <button
                    type="button"
                    aria-label={`inspect-surface-${surface.id}`}
                    onClick={() => onInspectSurface(surface.id, displayName)}
                    className={`w-full min-h-11 py-1 text-sm rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 font-semibold hover:bg-emerald-100 transition ${INSPECT_BUTTON_WITH_BADGE}`}
                  >
                    <span className="min-w-0 break-words"><Ico>🔬</Ico>{t.inspections.inspect_wall}</span>
                    <InspectionPhotoBadge surfaceId={surface.id} />
                  </button>
                )}

                {isWall && partsCount > 0 && (
                  <div aria-label={`merged-parts-${surface.id}`} className="space-y-1 rounded-xl border border-blue-200/70 p-2">
                    <div className="flex flex-wrap items-center justify-between gap-x-2">
                      <span className="text-xs font-semibold text-slate-700 min-w-0 break-words">
                        <Ico>🔗</Ico>{t.surfaces.parts_title.replace('{count}', String(partsCount))}
                      </span>
                      <div className="flex items-center gap-1.5">
                      {effectiveWallMode === 'CUSTOM' && !surface.is_archived && (
                        <button
                          type="button"
                          aria-label={`duplicate-merged-${surface.id}`}
                          onClick={() => void handleDuplicateMerged(surface)}
                          disabled={mergeBusy}
                          className="group shrink-0 min-h-11 flex items-center text-xs font-medium disabled:opacity-60"
                        >
                          <span className="rounded-lg bg-indigo-50 px-2.5 py-1 text-indigo-700 group-hover:bg-indigo-100 transition">
                            <Ico>📑</Ico>{t.surfaces.duplicate_wall}
                          </span>
                        </button>
                      )}
                      <button
                        type="button"
                        aria-label={`unmerge-surface-${surface.id}`}
                        onClick={() => setUnmergeConfirmId(unmergeConfirmId === surface.id ? null : surface.id)}
                        disabled={mergeBusy}
                        className="group shrink-0 min-h-11 flex items-center text-xs font-medium disabled:opacity-60"
                      >
                        <span className="rounded-lg bg-slate-100 px-2.5 py-1 text-slate-700 group-hover:bg-slate-200 transition">{t.surfaces.unmerge}</span>
                      </button>
                      </div>
                    </div>
                    {unmergeConfirmId === surface.id && (
                      <div role="alertdialog" aria-label={`unmerge-confirm-${surface.id}`} className="space-y-2 rounded-lg bg-amber-50 p-2">
                        <p className="text-xs text-amber-900 break-words">{t.surfaces.unmerge_confirm}</p>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            aria-label={`unmerge-confirm-yes-${surface.id}`}
                            onClick={() => void handleUnmerge(surface.id)}
                            disabled={mergeBusy}
                            className="min-h-11 flex-1 px-3 text-sm rounded-xl bg-blue-600 text-white font-semibold disabled:opacity-60"
                          >
                            {t.surfaces.unmerge_confirm_yes}
                          </button>
                          <button
                            type="button"
                            onClick={() => setUnmergeConfirmId(null)}
                            className="min-h-11 flex-1 px-3 text-sm rounded-xl border border-slate-300 text-slate-700 font-medium"
                          >
                            {t.common.cancel}
                          </button>
                        </div>
                      </div>
                    )}
                    {(surface.parts ?? []).map((part, partIndex) => (
                      <div key={part.id} aria-label={`merged-part-${part.id}`}>
                        <p className="text-[11px] text-slate-500">{t.surfaces.part_label.replace('{n}', String(partIndex + 1))}</p>
                        <SurfaceDimensions
                          surfaceId={part.id}
                          width={part.width}
                          height={part.height}
                          readOnly={surface.is_archived}
                          onSave={(width, height) => savePartSize(surface.id, part.id, width, height)}
                        />
                      </div>
                    ))}
                  </div>
                )}
                {/* the size, with a one-tap way to change it right on the card (Stage 19, owner request) */}
                {partsCount === 0 && <SurfaceDimensions
                  surfaceId={surface.id}
                  width={surface.width}
                  height={surface.height}
                  readOnly={surface.is_archived}
                  onSave={(width, height) => saveDimensions(surface.id, width, height)}
                  extraAction={
                    isWall && effectiveWallMode === 'CUSTOM' && hasDimensions && !surface.is_archived && partsCount === 0 ? (
                      <button
                        type="button"
                        aria-label={`duplicate-surface-${surface.id}`}
                        onClick={() => void handleDuplicateWall(surface)}
                        className="group min-h-11 shrink-0 flex items-center text-xs font-medium"
                      >
                        <span className="rounded-lg bg-indigo-50 px-2.5 py-1 text-indigo-700 group-hover:bg-indigo-100 transition">
                          <Ico>📑</Ico>{t.surfaces.duplicate_wall}
                        </span>
                      </button>
                    ) : undefined
                  }
                />}

                {openingSummary.length > 0 && (
                  <div aria-label={`openings-summary-${surface.id}`} className="text-xs text-slate-600">
                    <span className="font-semibold text-slate-700">{t.surfaces.openings_summary_title}</span>
                    <ul className="mt-0.5 space-y-0.5">
                      {openingSummary.map((row) => (
                        <li key={`${row.openingType}-${row.width}-${row.height}`} className="break-words">
                          {openingTypeLabel(row.openingType)} {formatOpeningDimension(row.width)} × {formatOpeningDimension(row.height)} {t.common.unit_m}{' '}
                          <span className="font-semibold text-slate-900">({row.count})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {isWall ? (
                  <>
                    {waitingArea ? (
                      // a wall only the phone knows: the typed width × height, marked "~" (owner decision Q5 (b))
                      <p aria-label={`surface-preview-${surface.id}`} className="bg-sky-50 border border-sky-200 rounded-xl p-3 text-xs text-sky-900 break-words">
                        <strong className="text-sm">~{waitingArea} {t.common.unit_m2}</strong>
                        <span className="block mt-0.5">{t.offline.area_after_sync}</span>
                      </p>
                    ) : hasDimensions ? (
                      <div className="space-y-1.5">
                        {/* Usability U-7: the net area is the one figure of the card; a tap on it opens the calculation (gross, openings, reveals). */}
                        <button
                          type="button"
                          aria-label={`area-details-${surface.id}`}
                          aria-expanded={!!expandedAreas[surface.id]}
                          onClick={() => toggleAreaDetails(surface.id)}
                          className="w-full min-h-11 flex items-center justify-between gap-2 bg-emerald-50 border border-emerald-200/60 rounded-lg px-2 py-1.5 text-left"
                        >
                          <span className="flex items-center gap-1 text-[11px] text-emerald-800 font-medium min-w-0 break-words">
                            <span aria-hidden="true">=</span>
                            <span>{t.surfaces.net_area}</span>
                          </span>
                          <strong className="shrink-0 text-emerald-700 text-xs font-bold">
                            {formatMetric(surface.net_area ?? surface.gross_area)} {t.common.unit_m2}
                            <span aria-hidden="true" className="ml-1">{expandedAreas[surface.id] ? '▴' : '▾'}</span>
                          </strong>
                        </button>
                        {expandedAreas[surface.id] && (
                      <div aria-label={`area-calculation-${surface.id}`} className="bg-slate-50 border border-slate-200/80 rounded-xl p-3 text-xs space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[11px] text-slate-500">{t.surfaces.gross_area}</span>
                          <strong className="text-slate-800 text-xs font-semibold">
                            {formatMetric(surface.gross_area)} {t.common.unit_m2}
                          </strong>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-1 text-[11px] text-slate-500 min-w-0">
                            <span aria-hidden="true" className="shrink-0">−</span>
                            <span className="break-words">
                              {t.surfaces.deduction_area}
                              {deductionContext && ` (${deductionContext})`}
                            </span>
                          </span>
                          <strong className="text-slate-700 text-xs font-semibold shrink-0">
                            {formatMetric(surface.deduction_area ?? '0.000')} {t.common.unit_m2}
                          </strong>
                        </div>
                        {revealAggregate && (
                          <div className="flex items-center justify-between gap-2">
                            <span className="flex items-center gap-1 text-[11px] text-slate-500">
                              <span aria-hidden="true">−</span>
                              <span>{t.surfaces.reveal_row_label}</span>
                            </span>
                            <strong className="text-slate-700 text-xs font-semibold shrink-0">
                              {formatMetric(revealAggregate.length)} {t.pricebook.units.LM} / {formatMetric(revealAggregate.area)} {t.common.unit_m2}
                            </strong>
                          </div>
                        )}
                      </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-2 py-1.5">
                        {t.surfaces.requires_dimensions}
                      </p>
                    )}

                    {surface.description && <p className="text-xs text-slate-500">{surface.description}</p>}

                    <PlanExecutionTabs surfaceId={surface.id} planOpen={isWorkPlanOpen} executionOpen={isExecutionOpen} onPlan={() => toggleWorkPlan(surface.id)} onExecution={() => toggleExecution(surface.id)} />

                    {isWorkPlanOpen && (
                      <SurfaceWorkPlanEditor
                        projectId={projectId}
                        roomId={roomId}
                        surfaceId={surface.id}
                        surfaceName={displayName}
                        isWall={true}
                        otherActiveWallCount={activeWallCount - 1}
                        surfaceType={surface.surface_type}
                        surfaceNames={Object.fromEntries(
                          all.map((s) => [s.id, getSurfaceDisplayName(s, surfaceDisplayLabels)]),
                        )}
                        onClose={() => setActiveWorkPlanSurfaceId(null)}
                      />
                    )}


                    {isExecutionOpen && (
                      <SurfaceExecutionView
                        projectId={projectId}
                        roomId={roomId}
                        surfaceId={surface.id}
                        surfaceName={displayName}
                        onClose={() => setActiveExecutionSurfaceId(null)}
                        onOpenPlan={() => openWorkPlanFromExecution(surface.id)}
                        isWall={true}
                        otherActiveWallCount={activeWallCount - 1}
                        surfaceNames={Object.fromEntries(
                          all.map((s) => [s.id, getSurfaceDisplayName(s, surfaceDisplayLabels)]),
                        )}
                      />
                    )}

                    {isOptionsOpen && (
                      <>
                        {/* Actions: 2-column grid with ~44px touch targets */}
                        <div className="grid grid-cols-2 gap-2">
                          {hasDimensions && (
                            <>
                              <button
                                type="button"
                                aria-label={`add-opening-${surface.id}-DOOR`}
                                onClick={() => quickAddOpening(surface.id, 'DOOR')}
                                className="min-h-11 w-full text-xs px-2 py-1 rounded-lg bg-emerald-50 text-emerald-800 font-semibold hover:bg-emerald-100 transition"
                              >
                                <Ico>🚪</Ico>{t.openings.door}
                              </button>
                              <button
                                type="button"
                                aria-label={`add-opening-${surface.id}-WINDOW`}
                                onClick={() => quickAddOpening(surface.id, 'WINDOW')}
                                className="min-h-11 w-full text-xs px-2 py-1 rounded-lg bg-sky-50 text-sky-800 font-semibold hover:bg-sky-100 transition"
                              >
                                <Ico>🪟</Ico>{t.openings.window}
                              </button>
                              <button
                                type="button"
                                aria-label={`add-opening-${surface.id}-OTHER`}
                                onClick={() => quickAddOpening(surface.id, 'OTHER')}
                                className="min-h-11 w-full text-xs px-2 py-1 rounded-lg bg-slate-100 text-slate-700 font-semibold hover:bg-slate-200 transition"
                              >
                                <Ico>⬜</Ico>{t.openings.other}
                              </button>
                              <button
                                type="button"
                                aria-label={`toggle-openings-${surface.id}`}
                                onClick={() => toggleOpenings(surface.id)}
                                className={`min-h-11 w-full text-xs px-2 py-1 rounded-lg font-semibold transition ${
                                  isOpeningsOpen
                                    ? 'bg-slate-200 text-slate-800'
                                    : 'bg-blue-100 text-blue-800 hover:bg-blue-200'
                                }`}
                              >
                                <Ico>{isOpeningsOpen ? '🔼' : '📋'}</Ico>
                                {isOpeningsOpen ? t.openings.close : t.surfaces.manage_openings}
                              </button>
                            </>
                          )}
                          <button
                            type="button"
                            aria-label={`edit-surface-${surface.id}`}
                            onClick={() => startEdit(surface)}
                            className="min-h-11 w-full text-xs px-2 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                          >
                            <Ico>✏️</Ico>{t.common.edit}
                          </button>
                          {!(surface.is_archived && surface.merged_into_id) && <button
                            type="button"
                            aria-label={`${surface.is_archived ? 'restore' : 'archive'}-surface-${surface.id}`}
                            onClick={() => void changeArchiveState(surface)}
                            className="min-h-11 w-full text-xs px-2 py-1 rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                          >
                            <Ico>{surface.is_archived ? '♻️' : '🗃️'}</Ico>{surface.is_archived ? t.common.restore : t.common.archive}
                          </button>}
                        </div>

                        {isOpeningsOpen && (
                          <OpeningList
                            key={pendingQuickOpening?.surfaceId === surface.id ? `quick-${pendingQuickOpening.key}` : surface.id}
                            projectId={projectId}
                            roomId={roomId}
                            surfaceId={surface.id}
                            initialType={pendingQuickOpening?.surfaceId === surface.id ? pendingQuickOpening.type : undefined}
                            onOpeningChanged={handleOpeningChanged}
                          />
                        )}

                        {/* Bottom collapse mirrors the top Opcje toggle so a long
                            expanded openings panel never forces a scroll back up. */}
                        <button
                          type="button"
                          aria-label={`options-toggle-bottom-${surface.id}`}
                          aria-expanded={isOptionsOpen}
                          onClick={() => toggleOptions(surface.id)}
                          className="w-full min-h-11 text-sm px-3 py-1 rounded-xl bg-slate-100 text-slate-800 font-semibold hover:bg-slate-200 transition"
                        >
                          <Ico>🔼</Ico>
                          {t.surfaces.hide_openings_and_options}
                        </button>
                      </>
                    )}
                  </>
                ) : (
                  <>
                    {surface.gross_area && (
                      <p className="text-xs text-slate-600">
                        <span>{t.surfaces.gross_area}: </span>
                        <strong className="text-slate-800">{formatMetric(surface.gross_area)} {t.common.unit_m2}</strong>
                      </p>
                    )}
                    {surface.description && <p className="text-xs text-slate-500">{surface.description}</p>}

                    <PlanExecutionTabs surfaceId={surface.id} planOpen={isWorkPlanOpen} executionOpen={isExecutionOpen} onPlan={() => toggleWorkPlan(surface.id)} onExecution={() => toggleExecution(surface.id)} />

                    {isWorkPlanOpen && (
                      <SurfaceWorkPlanEditor
                        projectId={projectId}
                        roomId={roomId}
                        surfaceId={surface.id}
                        surfaceName={displayName}
                        surfaceType={surface.surface_type}
                        onClose={() => setActiveWorkPlanSurfaceId(null)}
                      />
                    )}


                    {isExecutionOpen && (
                      <SurfaceExecutionView
                        projectId={projectId}
                        roomId={roomId}
                        surfaceId={surface.id}
                        surfaceName={displayName}
                        onClose={() => setActiveExecutionSurfaceId(null)}
                        onOpenPlan={() => openWorkPlanFromExecution(surface.id)}
                      />
                    )}

                    {isOptionsOpen && (
                      <div className="flex gap-2 flex-wrap">
                        <button
                          type="button"
                          aria-label={`edit-surface-${surface.id}`}
                          onClick={() => startEdit(surface)}
                          className="min-h-11 px-3 py-1 text-xs rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                        >
                          <Ico>✏️</Ico>{t.common.edit}
                        </button>
                        <button
                          type="button"
                          aria-label={`${surface.is_archived ? 'restore' : 'archive'}-surface-${surface.id}`}
                          onClick={() => void changeArchiveState(surface)}
                          className="min-h-11 px-3 py-1 text-xs rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                        >
                          <Ico>{surface.is_archived ? '♻️' : '🗃️'}</Ico>{surface.is_archived ? t.common.restore : t.common.archive}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {selecting && (
        <>
          <div aria-hidden="true" className="h-28" />
          <div
            aria-label="merge-bar"
            className="fixed inset-x-0 z-30 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] border-t px-4 py-2"
            style={{ backgroundColor: 'var(--tg-theme-bg-color)', borderColor: 'var(--tg-theme-secondary-bg-color)' }}
          >
            <div className="mx-auto w-full max-w-lg space-y-2">
              {mergeConfirm && selectedIds.length >= 2 ? (
                <div role="alertdialog" aria-label="merge-confirm" className="space-y-2">
                  <p className="text-sm font-semibold text-[var(--tg-theme-text-color)]">{t.surfaces.merge_confirm_title}</p>
                  <p className="text-xs text-slate-600 break-words">{t.surfaces.merge_confirm_body.replace('{name}', nameOf(selectedIds[0]))}</p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      aria-label="merge-confirm-yes"
                      onClick={() => void handleMerge()}
                      disabled={mergeBusy}
                      className="min-h-11 flex-1 px-3 text-sm rounded-xl bg-blue-600 text-white font-semibold disabled:opacity-60"
                    >
                      {t.surfaces.merge_confirm_yes}
                    </button>
                    <button
                      type="button"
                      aria-label="merge-confirm-back"
                      onClick={() => setMergeConfirm(false)}
                      className="min-h-11 flex-1 px-3 text-sm rounded-xl border border-slate-300 text-slate-700 font-medium"
                    >
                      {t.common.cancel}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span aria-label="merge-selected" className="min-w-0 flex-1 text-xs text-slate-600 break-words">
                    {t.surfaces.merge_selected.replace('{count}', String(selectedIds.length))}
                  </span>
                  <button
                    type="button"
                    aria-label="merge-cancel"
                    onClick={stopSelecting}
                    className="shrink-0 min-h-11 px-3 text-sm rounded-xl border border-slate-300 text-slate-700 font-medium"
                  >
                    {t.common.cancel}
                  </button>
                  <button
                    type="button"
                    aria-label="merge-go"
                    disabled={selectedIds.length < 2 || mergeBusy}
                    onClick={() => setMergeConfirm(true)}
                    className="shrink-0 min-h-11 px-3 text-sm rounded-xl bg-blue-600 text-white font-semibold disabled:opacity-50"
                  >
                    {t.surfaces.merge_action.replace('{count}', String(selectedIds.length))}
                  </button>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
