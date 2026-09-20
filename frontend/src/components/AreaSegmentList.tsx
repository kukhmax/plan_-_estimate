import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  archiveAreaSegment,
  createAreaSegment,
  fetchAreaSegments,
  restoreAreaSegment,
  updateAreaSegment,
} from '../api/areaSegments';
import { fetchSurfaces } from '../api/surfaces';
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
import { SurfaceWorkPlanEditor } from './SurfaceWorkPlanEditor';

interface AreaSegmentListProps {
  projectId: string;
  roomId: string;
  onMeasurementChanged?: () => void;
}

interface SegmentFormState {
  plane: AreaPlane;
  operation: AreaOperation;
  width: string;
  height: string;
  label: string;
}

const PLANES: AreaPlane[] = ['FLOOR', 'CEILING'];

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
  onMeasurementChanged,
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
  const [activeWorkPlanPlane, setActiveWorkPlanPlane] = useState<AreaPlane | null>(null);
  /** Canonical plane Surface (Stage 10C.1A) resolved from the room's surface rows. */
  const [planeSurfaces, setPlaneSurfaces] = useState<Record<AreaPlane, SurfaceType | null>>({
    FLOOR: null,
    CEILING: null,
  });

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
  }, [projectId, roomId, t.area_segments.error]);

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
    setForm({ plane, operation, width: '', height: '', label: '' });
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
    setActiveWorkPlanPlane((current) => current === plane ? null : plane);
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
    const isOptionsOpen = !!expandedOptions[plane];
    const planeSurface = planeSurfaces[plane];
    const planeSurfaceId = planeSurface?.id ?? null;
    const displayName = planeSurface
      ? getSurfaceDisplayName(planeSurface, surfaceDisplayLabels)
      : planeLabel(plane);
    const isWorkPlanOpen = activeWorkPlanPlane === plane;
    const tint = surfaceTypeTint(plane);

    return (
      <section
        key={plane}
        aria-label={`${planeKey}-segments`}
        className={`${tint.bg} border ${tint.border} rounded-2xl p-4 shadow-sm space-y-2.5`}
      >
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h4 className="text-sm font-semibold text-slate-900">{displayName}</h4>
          {hasPlaneArea && (
            // White background regardless of plane tint — a colored-on-colored
            // badge (e.g. FLOOR's own emerald tint) would lose contrast.
            <span className="text-xs px-2 py-0.5 rounded-full bg-white text-emerald-700 font-semibold">
              {t.area_segments.total}: {formatMetric(totals.net)} {t.common.unit_m2}
            </span>
          )}
        </div>

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

        {/* Progressive disclosure: Opcje reveals the plane's measurement actions. */}
        <button
          type="button"
          aria-label={`options-toggle-${planeKey}`}
          aria-expanded={isOptionsOpen}
          onClick={() => toggleOptions(plane)}
          className="w-full min-h-11 text-sm px-3 rounded-xl bg-slate-100 text-slate-800 font-semibold hover:bg-slate-200 transition"
        >
          {isOptionsOpen ? t.surfaces.hide_options : t.surfaces.options}
        </button>

        {planeSurfaceId && (
          <>
            <button
              type="button"
              aria-label={`work-plan-${planeSurfaceId}`}
              aria-expanded={isWorkPlanOpen}
              aria-controls={`work-plan-editor-${planeSurfaceId}`}
              onClick={() => toggleWorkPlan(plane)}
              className="w-full min-h-11 text-sm px-3 rounded-xl bg-slate-50 text-slate-700 font-medium hover:bg-slate-100 transition"
            >
              {t.surfaces.work_types_quality}
            </button>

            {isWorkPlanOpen && (
              <SurfaceWorkPlanEditor
                projectId={projectId}
                roomId={roomId}
                surfaceId={planeSurfaceId}
                surfaceName={displayName}
                onClose={() => setActiveWorkPlanPlane(null)}
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
                className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-50 text-emerald-800 font-semibold hover:bg-emerald-100 transition"
              >
                + {t.area_segments.add_rectangle}
              </button>
              <button
                type="button"
                aria-label={`add-${planeKey}-subtraction`}
                onClick={() => startAdd(plane, 'SUBTRACT')}
                className="text-xs px-2.5 py-1.5 rounded-lg bg-rose-50 text-rose-700 font-semibold hover:bg-rose-100 transition"
              >
                + {t.area_segments.add_subtraction}
              </button>
            </div>

            {activeForm && (
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
                    <input
                      aria-label="segment-width"
                      type="number"
                      inputMode="decimal"
                      min="0.001"
                      step="any"
                      placeholder="2.000"
                      autoFocus
                      value={activeForm.width}
                      onChange={(e) =>
                        setForm((cur) => (cur ? { ...cur, width: e.target.value } : cur))
                      }
                      className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">
                      {t.area_segments.length}
                    </label>
                    <input
                      aria-label="segment-height"
                      type="number"
                      inputMode="decimal"
                      min="0.001"
                      step="any"
                      placeholder="2.000"
                      value={activeForm.height}
                      onChange={(e) =>
                        setForm((cur) => (cur ? { ...cur, height: e.target.value } : cur))
                      }
                      className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
                    />
                  </div>
                </div>
                <input
                  aria-label="segment-label"
                  type="text"
                  maxLength={255}
                  placeholder={t.area_segments.label}
                  value={activeForm.label}
                  onChange={(e) =>
                    setForm((cur) => (cur ? { ...cur, label: e.target.value } : cur))
                  }
                  className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
                />
                {formError && (
                  <p role="alert" className="text-sm text-red-600 font-medium">{formError}</p>
                )}
                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={closeForm}
                    className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-100"
                  >
                    {t.common.cancel}
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-2.5 py-1.5 text-xs bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
                  >
                    {saving ? t.common.saving : t.common.save}
                  </button>
                </div>
              </form>
            )}

            {planeSegments.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-2">
                {plane === 'FLOOR'
                  ? t.area_segments.empty_floor
                  : t.area_segments.empty_ceiling}
              </p>
            ) : (
              <ul className="space-y-1.5">
                {planeSegments.map((segment) => (
                  <li
                    key={segment.id}
                    aria-label={`segment-item-${segment.id}`}
                    className="flex items-center justify-between gap-2 bg-slate-50 border border-slate-200/80 rounded-lg px-2.5 py-2 text-xs"
                  >
                    <div className="min-w-0 flex-1">
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
                          <span className="font-semibold text-slate-800 truncate">
                            {segment.label}
                          </span>
                        )}
                      </div>
                      <p className="text-slate-500 mt-0.5">
                        {formatMetric(segment.width)} × {formatMetric(segment.height)} {t.common.unit_m} ={' '}
                        <strong className="text-slate-800">
                          {formatMetric(segment.area ?? segmentArea(segment))} {t.common.unit_m2}
                        </strong>
                      </p>
                    </div>
                    <div className="flex gap-1.5 flex-wrap justify-end flex-shrink-0">
                      <button
                        type="button"
                        aria-label={`edit-segment-${segment.id}`}
                        onClick={() => startEdit(segment)}
                        className="text-xs px-2 py-1.5 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                      >
                        {t.common.edit}
                      </button>
                      <button
                        type="button"
                        aria-label={`${segment.is_archived ? 'restore' : 'archive'}-segment-${segment.id}`}
                        onClick={() => void changeArchiveState(segment)}
                        className="text-xs px-2 py-1.5 rounded-lg bg-slate-100 text-slate-600 font-medium hover:bg-slate-200 transition"
                      >
                        {segment.is_archived ? t.common.restore : t.common.archive}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>
    );
  };

  return (
    <section aria-label="area-segments-section" className="w-full mt-5 space-y-3">
      <h3 className="text-lg font-bold text-slate-900">{t.area_segments.title}</h3>
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
