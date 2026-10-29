import { INSPECT_BUTTON_WITH_BADGE, InspectionPhotoBadge } from './ExecutionPhotoBadge';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  archiveAreaSegment,
  createAreaSegment,
  fetchAreaSegments,
  reorderAreaSegments,
  restoreAreaSegment,
  updateAreaSegment,
} from '../api/areaSegments';
import { fetchSurfaces } from '../api/surfaces';
import { ApiError } from '../api/http';
import { moveItem, useDragReorder } from '../hooks/useDragReorder';
import { useI18n } from '../hooks/useI18n';
import {
  AreaOperation,
  AreaPlane,
  AreaSegmentType,
  PlaneAreaSummary,
} from '../types/areaSegment';
import { SurfaceType } from '../types/surface';
import { formatMetric } from '../utils/format';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { surfaceTypeTint } from '../utils/surfaceTypeTint';
import { PhotoCardButton, PhotoCardPanel } from './PhotoCard';
import { SurfaceExecutionView } from './SurfaceExecutionView';
import { SurfaceWorkPlanEditor } from './SurfaceWorkPlanEditor';
import { DimensionInput } from './DimensionInput';
import { Ico } from './Ico';
import { PlanExecutionTabs } from './PlanExecutionTabs';
import { PendingMark } from './PendingMark';
import { SurfaceRowButton } from './SurfaceRowButton';

interface AreaSegmentListProps {
  projectId: string;
  roomId: string;
  /** Room name for the photo caption path (Stage 14E.6); optional. */
  roomName?: string;
  /** Changes whenever the room size is corrected, so the cards re-read the recalculated planes. */
  dimensionsKey?: string;
  /** Open the floor and the ceiling cards on the first load (a collapsed row is the default). */
  initiallyOpen?: boolean;
  onMeasurementChanged?: () => void;
  /** Stage 13F-PRE: FLOOR / CEILING inspection lives in the plane's Opcje. */
  onInspectPlane?: (plane: AreaPlane) => void;
}

interface SegmentFormState {
  plane: AreaPlane;
  operation: AreaOperation;
  width: string;
  height: string;
  label: string;
  /** Also create the same rectangle on the opposite plane (floor <-> ceiling). */
  alsoOpposite: boolean;
}

const oppositePlane = (plane: AreaPlane): AreaPlane => (plane === 'FLOOR' ? 'CEILING' : 'FLOOR');

const PLANES: AreaPlane[] = ['FLOOR', 'CEILING'];
/** Planes with a real inspection checklist (13F-PRE FIX.2). The substrate
 * checklists are wall/ceiling finishing checklists; there is no floor
 * checklist yet ("Floor Inspection & Floor Preparation Catalog", deferred),
 * so FLOOR offers no inspection rather than a meaningless one. */
// the floor has its own checklists since UX walk B4 (screed, old tile, wooden boards); until then it offered no inspection
const INSPECTABLE_PLANES: readonly AreaPlane[] = ['FLOOR', 'CEILING'];

function segmentArea(segment: AreaSegmentType): number {
  const width = Number(segment.width);
  const height = Number(segment.height);
  if (Number.isNaN(width) || Number.isNaN(height)) return 0;
  return width * height;
}

function planeTotals(segments: AreaSegmentType[]): {
  additive: number;
  subtractive: number;
  net: number;
} {
  let additive = 0;
  let subtractive = 0;
  for (const segment of segments) {
    const value = segmentArea(segment);
    if (segment.operation === 'ADD') additive += value;
    else subtractive += value;
  }
  return { additive, subtractive, net: additive - subtractive };
}

export function AreaSegmentList({
  projectId,
  roomId,
  roomName,
  dimensionsKey,
  initiallyOpen = false,
  onMeasurementChanged,
  onInspectPlane,
}: AreaSegmentListProps) {
  const { t } = useI18n();
  const surfaceDisplayLabels = {
    wall: t.surfaces.wall,
    floor: t.surfaces.floor,
    ceiling: t.surfaces.ceiling,
  };
  const [segments, setSegments] = useState<AreaSegmentType[]>([]);
  const [planes, setPlanes] = useState<Record<AreaPlane, PlaneAreaSummary> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState<SegmentFormState | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  /** Per-plane Opcje progressive disclosure — UI state only, FLOOR independent of CEILING. */
  const [expandedOptions, setExpandedOptions] = useState<Partial<Record<AreaPlane, boolean>>>({});
  /** Which plane cards are open (the others are one-line rows); untouched planes follow `initiallyOpen`. */
  const [openPlanes, setOpenPlanes] = useState<Partial<Record<AreaPlane, boolean>>>({});
  const isPlaneOpen = (plane: AreaPlane) => openPlanes[plane] ?? initiallyOpen;
  const togglePlane = (plane: AreaPlane) => setOpenPlanes((current) => ({ ...current, [plane]: !(current[plane] ?? initiallyOpen) }));
  const [activeWorkPlanPlane, setActiveWorkPlanPlane] = useState<AreaPlane | null>(null);
  // Stage 13H.5: Realizacja is separate from the plan editor (one open at a time).
  const [activeExecutionPlane, setActiveExecutionPlane] = useState<AreaPlane | null>(null);
  /** Canonical plane Surface (Stage 10C.1A) resolved from the room's surface rows. */
  const [planeSurfaces, setPlaneSurfaces] = useState<Record<AreaPlane, SurfaceType | null>>({
    FLOOR: null,
    CEILING: null,
  });

  /** Order mode of one plane (owner 2026-10-29, like the order of the walls): the rectangles get ↑ ↓ and a handle; every move is saved at once. */
  const [reorderingPlane, setReorderingPlane] = useState<AreaPlane | null>(null);
  const [orderBusy, setOrderBusy] = useState(false);
  const [orderError, setOrderError] = useState<string | null>(null);
  const idsOf = (plane: AreaPlane) => segments.filter((candidate) => candidate.plane === plane).map((candidate) => candidate.id);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAreaSegments(projectId, roomId);
      setSegments(data.items);
      setPlanes(data.planes ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.area_segments.error);
    } finally {
      setLoading(false);
    }
  }, [projectId, roomId, dimensionsKey, t.area_segments.error]);

  // Canonical plane identity comes from the room's real Surface rows, so it stays
  // available even when a plane has zero AreaSegment rows. If the surfaces fetch
  // fails the Work Plan entry stays hidden rather than fabricating an ID.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let floorSurface: SurfaceType | null = null;
      let ceilingSurface: SurfaceType | null = null;
      try {
        const surfaceData = await fetchSurfaces(projectId, roomId);
        for (const surface of surfaceData.items) {
          if (surface.is_archived) continue;
          if (surface.surface_type === 'FLOOR' && floorSurface === null) floorSurface = surface;
          else if (surface.surface_type === 'CEILING' && ceilingSurface === null) ceilingSurface = surface;
        }
      } catch {
        // canonical plane identity unavailable — no synthetic ID
      }
      if (!cancelled) setPlaneSurfaces({ FLOOR: floorSurface, CEILING: ceilingSurface });
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, roomId]);

  useEffect(() => {
    void load();
  }, [load]);

  const startAdd = (plane: AreaPlane, operation: AreaOperation) => {
    setSuccess(null);
    setEditingId(null);
    setFormError(null);
    setForm({ plane, operation, width: '', height: '', label: '', alsoOpposite: false });
  };

  const startEdit = (segment: AreaSegmentType) => {
    setSuccess(null);
    setEditingId(segment.id);
    setFormError(null);
    setForm({
      plane: segment.plane,
      operation: segment.operation,
      width: String(segment.width),
      height: String(segment.height),
      label: segment.label ?? '',
      alsoOpposite: false,
    });
  };

  const closeForm = () => {
    setForm(null);
    setEditingId(null);
    setFormError(null);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form) return;
    setSaving(true);
    setFormError(null);

    const widthVal = parseFloat(form.width.trim());
    const heightVal = parseFloat(form.height.trim());
    if (
      Number.isNaN(widthVal) || widthVal <= 0 ||
      Number.isNaN(heightVal) || heightVal <= 0
    ) {
      setFormError(t.area_segments.invalid);
      setSaving(false);
      return;
    }

    try {
      if (editingId) {
        await updateAreaSegment(projectId, roomId, editingId, {
          operation: form.operation,
          width: widthVal,
          height: heightVal,
          label: form.label.trim() || null,
        });
        setSuccess(t.area_segments.updated);
      } else {
        await createAreaSegment(projectId, roomId, {
          plane: form.plane,
          operation: form.operation,
          width: widthVal,
          height: heightVal,
          label: form.label.trim() || null,
        });
        setSuccess(t.area_segments.created);
        if (form.alsoOpposite) {
          const other = oppositePlane(form.plane);
          try {
            await createAreaSegment(projectId, roomId, {
              plane: other,
              operation: form.operation,
              width: widthVal,
              height: heightVal,
              label: form.label.trim() || null,
            });
            setSuccess(t.area_segments.created_both);
          } catch (err) {
            // the first rectangle is saved: say so, and what is missing
            closeForm();
            await load();
            onMeasurementChanged?.();
            setSuccess(null);
            setError(`${t.area_segments.copy_failed} ${err instanceof Error ? err.message : t.area_segments.error}`);
            return;
          }
        }
      }
      closeForm();
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t.area_segments.error);
    } finally {
      setSaving(false);
    }
  };

  /** Saves a new order of the rectangles of a plane: the screen answers at once, the server confirms (a refusal brings the real order back). */
  const saveSegmentOrder = async (plane: AreaPlane, next: string[]) => {
    setSegments((current) => {
      const slots = current.map((candidate, index) => (candidate.plane === plane ? index : -1)).filter((index) => index >= 0);
      if (slots.length !== next.length) return current;
      const byId = new Map(current.map((candidate) => [candidate.id, candidate]));
      const copy = [...current];
      slots.forEach((slot, i) => {
        copy[slot] = byId.get(next[i]) ?? copy[slot];
      });
      return copy;
    });
    setOrderBusy(true);
    setOrderError(null);
    try {
      await reorderAreaSegments(projectId, roomId, plane, next);
    } catch (err) {
      setOrderError(err instanceof ApiError && err.code === 'AREA_REORDER_NOT_CURRENT' ? t.area_segments.reorder_stale : t.area_segments.reorder_failed);
      await load(); // the list as it really is
    } finally {
      setOrderBusy(false);
    }
  };
  const moveSegment = async (plane: AreaPlane, ids: string[], segmentId: string, delta: -1 | 1) => {
    const from = ids.indexOf(segmentId);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= ids.length) return;
    await saveSegmentOrder(plane, moveItem(ids, from, to));
  };
  const floorDrag = useDragReorder({ ids: idsOf('FLOOR'), onDrop: (next) => void saveSegmentOrder('FLOOR', next), disabled: reorderingPlane !== 'FLOOR' || orderBusy });
  const ceilingDrag = useDragReorder({ ids: idsOf('CEILING'), onDrop: (next) => void saveSegmentOrder('CEILING', next), disabled: reorderingPlane !== 'CEILING' || orderBusy });

  /** The same rectangle once more on the same plane (the rooms of a staircase have many alike): the copy stands right behind the original. */
  const duplicateSegment = async (segment: AreaSegmentType) => {
    setError(null);
    setSuccess(null);
    try {
      const created = await createAreaSegment(projectId, roomId, {
        plane: segment.plane,
        operation: segment.operation,
        width: Number(segment.width),
        height: Number(segment.height),
        label: segment.label,
      });
      const ids = idsOf(segment.plane);
      const at = ids.indexOf(segment.id);
      if (at >= 0 && ids.length >= 1) {
        try {
          await reorderAreaSegments(projectId, roomId, segment.plane, [...ids.slice(0, at + 1), created.id, ...ids.slice(at + 1)]);
        } catch {
          // the copy exists and stands at the end of the list: the order can be set by hand
        }
      }
      setSuccess(t.area_segments.duplicated);
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.area_segments.error);
    }
  };

  const changeArchiveState = async (segment: AreaSegmentType) => {
    setError(null);
    setSuccess(null);
    try {
      if (segment.is_archived) {
        await restoreAreaSegment(projectId, roomId, segment.id);
        setSuccess(t.area_segments.restored);
      } else {
        await archiveAreaSegment(projectId, roomId, segment.id);
        setSuccess(t.area_segments.archived);
      }
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.area_segments.error);
    }
  };

  /** The same rectangle on the other plane (floor <-> ceiling): the room is usually the same size above and below. */
  const copyToOpposite = async (segment: AreaSegmentType) => {
    setError(null);
    setSuccess(null);
    try {
      await createAreaSegment(projectId, roomId, {
        plane: oppositePlane(segment.plane),
        operation: segment.operation,
        width: Number(segment.width),
        height: Number(segment.height),
        label: segment.label,
      });
      setSuccess(t.area_segments.copied);
      await load();
      onMeasurementChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.area_segments.error);
    }
  };

  const planeLabel = (plane: AreaPlane) =>
    plane === 'FLOOR' ? t.area_segments.floor : t.area_segments.ceiling;

  const operationLabel = (operation: AreaOperation) =>
    operation === 'ADD'
      ? t.area_segments.operation_add
      : t.area_segments.operation_subtract;

  const toggleOptions = (plane: AreaPlane) => {
    setExpandedOptions((current) => ({ ...current, [plane]: !current[plane] }));
  };

  const toggleWorkPlan = (plane: AreaPlane) => {
    setActiveExecutionPlane(null);
    setActiveWorkPlanPlane((current) => current === plane ? null : plane);
  };

  const toggleExecution = (plane: AreaPlane) => {
    setActiveWorkPlanPlane(null);
    setActiveExecutionPlane((current) => current === plane ? null : plane);
  };

  const renderPlaneSection = (plane: AreaPlane) => {
    const activeForm = form !== null && form.plane === plane ? form : null;
    const planeSegments = segments.filter((s) => s.plane === plane);
    const summary = planes?.[plane];
    const totals = summary
      ? { net: Number(summary.net_area) }
      : planeTotals(planeSegments);
    const rectangleBase = summary !== undefined && summary.base_area !== null;
    const hasPlaneArea = rectangleBase || planeSegments.length > 0;
    const planeKey = plane === 'FLOOR' ? 'floor' : 'ceiling';
    const planeDrag = plane === 'FLOOR' ? floorDrag : ceilingDrag;
    const isOptionsOpen = !!expandedOptions[plane];
    const planeSurface = planeSurfaces[plane];
    const planeSurfaceId = planeSurface?.id ?? null;
    const displayName = planeSurface
      ? getSurfaceDisplayName(planeSurface, surfaceDisplayLabels)
      : planeLabel(plane);
    const isWorkPlanOpen = activeWorkPlanPlane === plane;
    const isExecutionOpen = activeExecutionPlane === plane;
    const tint = surfaceTypeTint(plane);

    if (!isPlaneOpen(plane)) {
      return (
        <div key={plane}>
          <SurfaceRowButton
            surfaceId={planeSurfaceId}
            rowKey={`plane-${planeKey}`}
            name={displayName}
            area={hasPlaneArea ? `${formatMetric(totals.net)} ${t.common.unit_m2}` : '—'}
            className={`${tint.bg} border ${tint.border} ${tint.extra} rounded-xl px-3 py-1.5 min-h-11 w-full flex items-center gap-2 shadow-sm`}
            onOpen={() => togglePlane(plane)}
          />
        </div>
      );
    }

    // the form is drawn where the owner works: a new rectangle above the list, a rectangle being changed IN ITS OWN PLACE (Stage 19, owner request)
    const segmentForm = activeForm ? (
        <form
          aria-label={`${planeKey}-segment-form`}
          onSubmit={handleSubmit}
          className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2.5"
        >
          <div className="flex items-center justify-between flex-wrap gap-1">
            <h5 className="text-xs font-semibold text-slate-700">
              {editingId ? t.area_segments.edit : t.area_segments.add}
            </h5>
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">
              {operationLabel(activeForm.operation)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-slate-500 mb-1">
                {t.area_segments.width}
              </label>
              <DimensionInput
                aria-label="segment-width"
                placeholder="200"
                autoFocus
                value={activeForm.width}
                onValueChange={(meters) =>
                  setForm((cur) => (cur ? { ...cur, width: meters } : cur))
                }
                className="w-full min-h-11 border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">
                {t.area_segments.length}
              </label>
              <DimensionInput
                aria-label="segment-height"
                placeholder="200"
                value={activeForm.height}
                onValueChange={(meters) =>
                  setForm((cur) => (cur ? { ...cur, height: meters } : cur))
                }
                className="w-full min-h-11 border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
              />
            </div>
          </div>
          {!editingId && (
            <button
              type="button"
              aria-label="segment-also-opposite"
              aria-pressed={activeForm.alsoOpposite}
              onClick={() => setForm((cur) => (cur ? { ...cur, alsoOpposite: !cur.alsoOpposite } : cur))}
              className={`w-full min-h-11 px-3 py-1 text-sm rounded-xl border font-semibold transition ${
                activeForm.alsoOpposite
                  ? 'bg-blue-600 border-blue-600 text-white'
                  : 'pe-surface border-slate-200 text-slate-700 hover:bg-slate-100'
              }`}
            >
              <Ico>{activeForm.alsoOpposite ? '☑️' : '🔁'}</Ico>
              {activeForm.plane === 'FLOOR' ? t.area_segments.also_ceiling : t.area_segments.also_floor}
            </button>
          )}
          <input
            aria-label="segment-label"
            type="text"
            maxLength={255}
            placeholder={t.area_segments.label}
            value={activeForm.label}
            onChange={(e) =>
              setForm((cur) => (cur ? { ...cur, label: e.target.value } : cur))
            }
            className="w-full min-h-11 border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
          />
          {formError && (
            <p role="alert" className="text-sm text-red-600 font-medium">{formError}</p>
          )}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={closeForm}
              className="min-h-11 px-3 py-1 text-xs rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-100"
            >
              <Ico>✖️</Ico>{t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="min-h-11 px-3 py-1 text-xs bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
            >
              <Ico>💾</Ico>{saving ? t.common.saving : t.common.save}
            </button>
          </div>
        </form>
    ) : null;

    return (
      <section
        key={plane}
        aria-label={`${planeKey}-segments`}
        className={`${tint.bg} border ${tint.border} ${tint.extra} rounded-2xl p-4 shadow-sm space-y-2.5`}
      >
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h4 className="text-sm font-semibold text-slate-900">
            <button
              type="button"
              aria-label={`plane-collapse-${planeKey}`}
              aria-expanded={true}
              onClick={() => togglePlane(plane)}
              className="min-h-11 flex items-center gap-2 text-left font-semibold"
            >
              <span aria-hidden="true" className="text-slate-500">▴</span>
              <span>{displayName}</span>
            </button>
          </h4>
          <div className="ml-auto flex items-center gap-2">
            {hasPlaneArea && (
              // White background regardless of plane tint — a colored-on-colored
              // badge (e.g. FLOOR's own emerald tint) would lose contrast.
              <span className="text-xs px-2 py-0.5 rounded-full pe-surface text-emerald-700 font-semibold">
                {t.area_segments.total}: {formatMetric(totals.net)} {t.common.unit_m2}
              </span>
            )}
            {/* Stage 14E.6 / 14E.7: photos are added on surfaces — the floor and the ceiling are surfaces too; the
                compact button shares the header line with the total. */}
            {planeSurfaceId && <PhotoCardButton context="SURFACE" targetId={planeSurfaceId} />}
          </div>
        </div>

        {planeSurfaceId && (
          <PhotoCardPanel
            context="SURFACE"
            targetId={planeSurfaceId}
            roomId={roomId}
            locationSegments={[roomName, displayName]}
          />
        )}

        {summary !== undefined && (
          <div className="text-xs text-slate-500 space-y-0.5 border-t border-slate-100 pt-1.5">
            {rectangleBase && (
              <p className="flex items-center justify-between gap-2">
                <span>{t.area_segments.base_area}</span>
                <span className="font-medium text-slate-700">
                  {formatMetric(summary.base_area)} {t.common.unit_m2}
                </span>
              </p>
            )}
            <p className="flex items-center justify-between gap-2">
              <span>{t.area_segments.adjustments}</span>
              <span className="font-medium text-slate-700">
                {formatMetric(summary.adjustment_area)} {t.common.unit_m2}
              </span>
            </p>
          </div>
        )}

        {/* The inspection is a main action of the plane: it stays outside Opcje (owner, Stage 18G). */}
        {onInspectPlane && INSPECTABLE_PLANES.includes(plane) && (
          <button
            type="button"
            aria-label={`inspect-${planeKey}`}
            onClick={() => onInspectPlane(plane)}
            className={`w-full min-h-11 py-1 text-sm rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 font-semibold hover:bg-emerald-100 transition ${INSPECT_BUTTON_WITH_BADGE}`}
          >
            <span className="min-w-0 break-words"><Ico>🔬</Ico>{plane === 'FLOOR' ? t.inspections.inspect_floor : t.inspections.inspect_ceiling}</span>
            <InspectionPhotoBadge surfaceId={planeSurfaceId} roomId={roomId} plane={plane} />
          </button>
        )}
        {/* Progressive disclosure: Opcje reveals the plane's measurement actions. */}
        <button
          type="button"
          aria-label={`options-toggle-${planeKey}`}
          aria-expanded={isOptionsOpen}
          onClick={() => toggleOptions(plane)}
          className="w-full min-h-11 text-sm px-3 py-1 rounded-xl bg-slate-100 text-slate-800 font-semibold hover:bg-slate-200 transition"
        >
          <Ico>{isOptionsOpen ? '🔼' : '⚙️'}</Ico>
          {isOptionsOpen ? t.surfaces.hide_options : t.surfaces.options}
        </button>

        {planeSurfaceId && (
          <>
            <PlanExecutionTabs surfaceId={planeSurfaceId} planOpen={isWorkPlanOpen} executionOpen={isExecutionOpen} onPlan={() => toggleWorkPlan(plane)} onExecution={() => toggleExecution(plane)} />

            {isWorkPlanOpen && (
              <SurfaceWorkPlanEditor
                projectId={projectId}
                roomId={roomId}
                surfaceId={planeSurfaceId}
                surfaceName={displayName}
                surfaceType={planeSurface?.surface_type}
                onClose={() => setActiveWorkPlanPlane(null)}
              />
            )}


            {isExecutionOpen && (
              <SurfaceExecutionView
                projectId={projectId}
                roomId={roomId}
                surfaceId={planeSurfaceId}
                surfaceName={displayName}
                onClose={() => setActiveExecutionPlane(null)}
                onOpenPlan={() => {
                  setActiveExecutionPlane(null);
                  setActiveWorkPlanPlane(plane);
                }}
              />
            )}
          </>
        )}

        {isOptionsOpen && (
          <>
            <div className="flex gap-2 flex-wrap">
              <button
                type="button"
                aria-label={`add-${planeKey}-rectangle`}
                onClick={() => startAdd(plane, 'ADD')}
                className="min-h-11 text-xs px-3 py-1 rounded-lg bg-emerald-50 text-emerald-800 font-semibold hover:bg-emerald-100 transition"
              >
                <Ico>➕</Ico>{t.area_segments.add_rectangle}
              </button>
              <button
                type="button"
                aria-label={`add-${planeKey}-subtraction`}
                onClick={() => startAdd(plane, 'SUBTRACT')}
                className="min-h-11 text-xs px-3 py-1 rounded-lg bg-rose-50 text-rose-700 font-semibold hover:bg-rose-100 transition"
              >
                <Ico>➖</Ico>{t.area_segments.add_subtraction}
              </button>
            </div>

            {!editingId && segmentForm}

            {planeSegments.length >= 2 && reorderingPlane !== plane && (
              <button
                type="button"
                aria-label={`reorder-${planeKey}-start`}
                onClick={() => {
                  setError(null);
                  setSuccess(null);
                  setOrderError(null);
                  closeForm();
                  setReorderingPlane(plane);
                }}
                className="w-full min-h-11 px-3 py-2 text-sm rounded-xl border border-slate-300 text-slate-700 font-semibold hover:bg-slate-100 transition"
              >
                <Ico>↕️</Ico>{t.surfaces.reorder_start}
              </button>
            )}

            {reorderingPlane === plane && (
              <div className="space-y-2">
                <p aria-label={`reorder-${planeKey}-hint`} className="text-xs text-slate-600 break-words">{t.area_segments.reorder_hint}</p>
                {orderError && <p role="alert" className="text-sm text-red-600 break-words">{orderError}</p>}
                <ul className="space-y-1.5">
                  {planeDrag.order.map((id) => planeSegments.find((candidate) => candidate.id === id)).filter((segment): segment is AreaSegmentType => !!segment).map((segment) => {
                    const ids = planeSegments.map((candidate) => candidate.id);
                    const at = ids.indexOf(segment.id);
                    const held = planeDrag.heldId === segment.id;
                    const arrow = 'shrink-0 min-h-11 min-w-11 rounded-xl border border-slate-300 text-lg font-bold text-slate-800 disabled:opacity-30';
                    const { ref: rowRef, ...holdProps } = planeDrag.rowProps(segment.id);
                    return (
                      <li
                        key={segment.id}
                        ref={rowRef}
                        {...holdProps}
                        aria-label={`segment-order-${segment.id}`}
                        data-held={held ? 'true' : undefined}
                        className={`bg-slate-50 border border-slate-200/80 rounded-xl pl-1 pr-2 py-1.5 min-h-11 w-full flex items-center gap-1.5 select-none transition-shadow ${held ? 'shadow-xl ring-2 ring-blue-500 scale-[1.02] relative z-10' : 'shadow-sm'}`}
                        style={{ WebkitTouchCallout: 'none' }}
                      >
                        <span
                          aria-label={`segment-drag-${segment.id}`}
                          title={t.area_segments.drag}
                          {...planeDrag.handleProps(segment.id)}
                          className="shrink-0 min-h-11 min-w-9 flex items-center justify-center text-xl text-slate-500 cursor-grab"
                          style={{ touchAction: 'none' }}
                        >
                          <span aria-hidden="true">⠿</span>
                        </span>
                        <span className="min-w-0 flex-1 text-xs">
                          <span className="flex items-center gap-1.5 flex-wrap">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${segment.operation === 'ADD' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-700'}`}>
                              {operationLabel(segment.operation)}
                            </span>
                            {segment.label && <span className="font-semibold text-slate-800 break-words">{segment.label}</span>}
                          </span>
                          <span className="block text-slate-500 break-words">
                            {formatMetric(segment.width)} × {formatMetric(segment.height)} {t.common.unit_m} = <strong className="text-slate-800">{formatMetric(segment.area ?? segmentArea(segment))} {t.common.unit_m2}</strong>
                          </span>
                        </span>
                        <button
                          type="button"
                          aria-label={`segment-up-${segment.id}`}
                          title={t.area_segments.move_up}
                          disabled={orderBusy || at <= 0}
                          onClick={() => void moveSegment(plane, ids, segment.id, -1)}
                          className={arrow}
                        >
                          <span aria-hidden="true">↑</span>
                        </button>
                        <button
                          type="button"
                          aria-label={`segment-down-${segment.id}`}
                          title={t.area_segments.move_down}
                          disabled={orderBusy || at < 0 || at >= ids.length - 1}
                          onClick={() => void moveSegment(plane, ids, segment.id, 1)}
                          className={arrow}
                        >
                          <span aria-hidden="true">↓</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                <button
                  type="button"
                  aria-label={`reorder-${planeKey}-done`}
                  onClick={() => setReorderingPlane(null)}
                  className="w-full min-h-11 px-3 text-sm rounded-xl bg-blue-600 text-white font-semibold"
                >
                  {t.surfaces.reorder_done}
                </button>
              </div>
            )}

            {reorderingPlane === plane ? null : planeSegments.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-2">
                {plane === 'FLOOR'
                  ? t.area_segments.empty_floor
                  : t.area_segments.empty_ceiling}
              </p>
            ) : (
              <ul className="space-y-1.5">
                {planeSegments.map((segment) =>
                  editingId === segment.id && segmentForm ? (
                  <li key={segment.id} aria-label={`segment-editing-${segment.id}`}>
                    {segmentForm}
                  </li>
                  ) : (
                  <li
                    key={segment.id}
                    aria-label={`segment-item-${segment.id}`}
                    className="flex flex-col gap-2 bg-slate-50 border border-slate-200/80 rounded-lg px-2.5 py-2 text-xs"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            segment.operation === 'ADD'
                              ? 'bg-emerald-100 text-emerald-800'
                              : 'bg-rose-100 text-rose-700'
                          }`}
                        >
                          {operationLabel(segment.operation)}
                        </span>
                        {segment.label && (
                          <span className="font-semibold text-slate-800 min-w-0 break-words">
                            {segment.label}
                          </span>
                        )}
                        <PendingMark record={segment} id={segment.id} />
                      </div>
                      <p className="text-slate-500 mt-0.5 break-words">
                        {formatMetric(segment.width)} × {formatMetric(segment.height)} {t.common.unit_m} ={' '}
                        <strong className="text-slate-800">
                          {formatMetric(segment.area ?? segmentArea(segment))} {t.common.unit_m2}
                        </strong>
                      </p>
                    </div>
                    {/* the buttons keep their own line: beside them the numbers were squeezed into a narrow column (owner, Stage 19) */}
                    <div className="flex gap-1.5 flex-wrap">
                      <button
                        type="button"
                        aria-label={`edit-segment-${segment.id}`}
                        onClick={() => startEdit(segment)}
                        className="min-h-11 text-xs px-2 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                      >
                        <Ico>✏️</Ico>{t.common.edit}
                      </button>
                      {!segment.is_archived && (
                        <button
                          type="button"
                          aria-label={`duplicate-segment-${segment.id}`}
                          onClick={() => void duplicateSegment(segment)}
                          className="min-h-11 text-xs px-2 py-1 rounded-lg bg-indigo-50 text-indigo-700 font-medium hover:bg-indigo-100 transition"
                        >
                          <Ico>📑</Ico>{t.area_segments.duplicate}
                        </button>
                      )}
                      {!segment.is_archived && (
                        <button
                          type="button"
                          aria-label={`copy-segment-${segment.id}`}
                          onClick={() => void copyToOpposite(segment)}
                          className="min-h-11 text-xs px-2 py-1 rounded-lg bg-indigo-50 text-indigo-700 font-medium hover:bg-indigo-100 transition"
                        >
                          <Ico>📋</Ico>
                          {segment.plane === 'FLOOR' ? t.area_segments.copy_to_ceiling : t.area_segments.copy_to_floor}
                        </button>
                      )}
                      <button
                        type="button"
                        aria-label={`${segment.is_archived ? 'restore' : 'archive'}-segment-${segment.id}`}
                        onClick={() => void changeArchiveState(segment)}
                        className="min-h-11 text-xs px-2 py-1 rounded-lg bg-slate-100 text-slate-600 font-medium hover:bg-slate-200 transition"
                      >
                        <Ico>{segment.is_archived ? '♻️' : '🗃️'}</Ico>{segment.is_archived ? t.common.restore : t.common.archive}
                      </button>
                    </div>
                  </li>
                  ),
                )}
              </ul>
            )}
          </>
        )}
      </section>
    );
  };

  return (
    <section aria-label="area-segments-section" className="w-full mt-5 space-y-3">
      <h3 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{t.area_segments.title}</h3>
      {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
      {loading && (
        <p className="text-sm text-slate-500 text-center py-4">{t.area_segments.loading}</p>
      )}
      {!loading && error && (
        <p role="alert" className="text-sm text-red-600 text-center py-4">{error}</p>
      )}
      {!loading && !error && PLANES.map((plane) => renderPlaneSection(plane))}
    </section>
  );
}
