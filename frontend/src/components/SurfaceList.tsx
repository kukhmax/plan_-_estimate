import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  archiveSurface,
  createSurface,
  fetchSurfaces,
  generateWalls,
  restoreSurface,
  updateSurface,
} from '../api/surfaces';
import { useI18n } from '../hooks/useI18n';
import { OpeningTypeValue } from '../types/opening';
import {
  SurfaceCreatePayload,
  SurfaceType,
  SurfaceTypeValue,
  SurfaceUpdatePayload,
} from '../types/surface';
import { formatMetric } from '../utils/format';
import { OpeningList } from './OpeningList';

interface SurfaceListProps {
  projectId: string;
  roomId: string;
  roomHeight?: string | number | null;
  hasRoomDimensions?: boolean;
  wallMode?: WallInputMode;
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
  roomHeight,
  hasRoomDimensions = false,
  wallMode,
  onMeasurementChanged,
  onInspectSurface,
}: SurfaceListProps) {
  const { t } = useI18n();
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
  const effectiveWallMode = wallMode ?? 'RECTANGLE';
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [pendingQuickOpening, setPendingQuickOpening] = useState<PendingQuickOpening | null>(null);
  const quickActionKeyRef = useRef(0);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : t.surfaces.error);
    } finally {
      setLoading(false);
    }
  }, [includeArchived, projectId, roomId, t.surfaces.error]);

  useEffect(() => {
    void load();
  }, [load]);

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

  return (
    <section aria-label="surfaces-section" className="w-full mt-5">
      <h3 className="text-lg font-bold text-slate-900 mb-3">{t.surfaces.title}</h3>

      {effectiveWallMode === 'RECTANGLE' && hasRoomDimensions && (
        <div className="mb-3">
          <button
            type="button"
            aria-label="generate-walls"
            onClick={() => void handleGenerateWalls()}
            disabled={generating}
            className="w-full px-3 py-2 text-sm bg-emerald-600 text-white font-semibold rounded-xl hover:bg-emerald-700 transition disabled:opacity-60"
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
          className="bg-white border border-slate-200 rounded-2xl p-4 mb-3 shadow-sm"
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
                <input
                  aria-label="custom-wall-width"
                  type="number"
                  inputMode="decimal"
                  min="0.001"
                  step="0.01"
                  placeholder="2.000"
                  autoFocus
                  value={customWall.width}
                  onChange={(e) => setCustomWall((cur) => ({ ...cur, width: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">{t.surfaces.height}</label>
                {customWall.differentHeight ? (
                  <input
                    aria-label="custom-wall-height"
                    type="number"
                    inputMode="decimal"
                    min="0.001"
                    step="0.01"
                    placeholder="2.700"
                    value={customWall.height}
                    onChange={(e) => setCustomWall((cur) => ({ ...cur, height: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm"
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

            <label className="flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer">
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
              className="w-full px-3 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              {saving ? t.common.saving : t.surfaces.add_wall}
            </button>
          </form>
        </div>
      )}

      <label className="flex items-center gap-1.5 text-sm text-slate-600 mb-3 cursor-pointer">
        <input
          aria-label="show-archived-surfaces"
          type="checkbox"
          checked={includeArchived}
          onChange={(event) => setIncludeArchived(event.target.checked)}
        />
        {t.common.show_archived}
      </label>

      {showForm && (
        <form
          aria-label="surface-form"
          onSubmit={handleSubmit}
          className="bg-white border border-slate-200 rounded-2xl p-4 mb-4 shadow-sm space-y-3"
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
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <select
            aria-label="surface-type"
            value={form.surface_type}
            onChange={(event) => setForm((current) => ({
              ...current,
              surface_type: event.target.value as SurfaceTypeValue,
            }))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            {(['WALL', 'CEILING', 'FLOOR', 'OTHER'] as const).map((value) => (
              <option key={value} value={value}>{typeLabel(value)}</option>
            ))}
          </select>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t.surfaces.width}</label>
              <input
                aria-label="surface-width"
                type="number"
                inputMode="decimal"
                min="0.001"
                step="0.01"
                placeholder="5.000"
                value={form.width}
                onChange={(event) => setForm((current) => ({ ...current, width: event.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t.surfaces.height}</label>
              <input
                aria-label="surface-height"
                type="number"
                inputMode="decimal"
                min="0.001"
                step="0.01"
                placeholder="2.700"
                value={form.height}
                onChange={(event) => setForm((current) => ({ ...current, height: event.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
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
              className="px-3 py-1.5 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
            >
              {t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              {saving ? t.common.saving : t.common.save}
            </button>
          </div>
        </form>
      )}

      {success && <p role="status" className="text-sm text-emerald-700 mb-3">{success}</p>}
      {loading && <p className="text-sm text-slate-500 text-center py-4">{t.surfaces.loading}</p>}
      {!loading && error && <p role="alert" className="text-sm text-red-600 text-center py-4">{error}</p>}
      {!loading && !error && surfaces.length === 0 && (
        <p aria-label="no-surfaces" className="text-sm text-slate-400 text-center py-6">
          {t.surfaces.empty}
        </p>
      )}
      {!loading && !error && surfaces.length > 0 && (
        <ul aria-label="surfaces-list" className="space-y-3">
          {surfaces.map((surface) => {
            const hasDimensions = surface.width !== null && surface.width !== undefined &&
                                  surface.height !== null && surface.height !== undefined;
            const isWall = surface.surface_type === 'WALL';
            const isOpeningsOpen = !!expandedOpenings[surface.id];

            return (
              <li
                key={surface.id}
                aria-label={`surface-item-${surface.id}`}
                className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-2.5"
              >
                {/* Header: name + badges */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-slate-900 text-sm min-w-0 break-words">{surface.name}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">
                    {typeLabel(surface.surface_type)}
                  </span>
                  {surface.is_archived && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                      {t.common.archived_badge}
                    </span>
                  )}
                </div>

                {hasDimensions && (
                  <p className="text-xs text-slate-600">
                    <span>{t.surfaces.dimensions}: </span>
                    <strong className="text-slate-900 font-semibold">
                      {formatMetric(surface.width)} × {formatMetric(surface.height)} {t.common.unit_m}
                    </strong>
                  </p>
                )}

                {isWall ? (
                  <>
                    {hasDimensions ? (
                      <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3 text-xs space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[11px] text-slate-500">{t.surfaces.gross_area}</span>
                          <strong className="text-slate-800 text-xs font-semibold">
                            {formatMetric(surface.gross_area)} {t.common.unit_m2}
                          </strong>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-1 text-[11px] text-slate-500">
                            <span aria-hidden="true">−</span>
                            <span>{t.surfaces.deduction_area}</span>
                          </span>
                          <strong className="text-slate-700 text-xs font-semibold">
                            {formatMetric(surface.deduction_area ?? '0.000')} {t.common.unit_m2}
                          </strong>
                        </div>
                        <div className="flex items-center justify-between gap-2 bg-emerald-50 border border-emerald-200/60 rounded-lg px-2 py-1.5">
                          <span className="flex items-center gap-1 text-[11px] text-emerald-800 font-medium">
                            <span aria-hidden="true">=</span>
                            <span>{t.surfaces.net_area}</span>
                          </span>
                          <strong className="text-emerald-700 text-xs font-bold">
                            {formatMetric(surface.net_area ?? surface.gross_area)} {t.common.unit_m2}
                          </strong>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-2 py-1.5">
                        {t.surfaces.requires_dimensions}
                      </p>
                    )}

                    {surface.description && <p className="text-xs text-slate-500">{surface.description}</p>}

                    {/* Actions: 2-column grid with ~44px touch targets */}
                    <div className="grid grid-cols-2 gap-2">
                      {onInspectSurface && (
                        <button
                          type="button"
                          aria-label={`inspect-surface-${surface.id}`}
                          onClick={() => onInspectSurface(surface.id, surface.name)}
                          className="min-h-11 w-full text-xs px-2 rounded-lg bg-violet-50 text-violet-800 font-semibold hover:bg-violet-100 transition"
                        >
                          {t.inspections.inspect_wall}
                        </button>
                      )}
                      {hasDimensions && (
                        <>
                          <button
                            type="button"
                            aria-label={`add-opening-${surface.id}-DOOR`}
                            onClick={() => quickAddOpening(surface.id, 'DOOR')}
                            className="min-h-11 w-full text-xs px-2 rounded-lg bg-emerald-50 text-emerald-800 font-semibold hover:bg-emerald-100 transition"
                          >
                            + {t.openings.door}
                          </button>
                          <button
                            type="button"
                            aria-label={`add-opening-${surface.id}-WINDOW`}
                            onClick={() => quickAddOpening(surface.id, 'WINDOW')}
                            className="min-h-11 w-full text-xs px-2 rounded-lg bg-sky-50 text-sky-800 font-semibold hover:bg-sky-100 transition"
                          >
                            + {t.openings.window}
                          </button>
                          <button
                            type="button"
                            aria-label={`add-opening-${surface.id}-OTHER`}
                            onClick={() => quickAddOpening(surface.id, 'OTHER')}
                            className="min-h-11 w-full text-xs px-2 rounded-lg bg-slate-100 text-slate-700 font-semibold hover:bg-slate-200 transition"
                          >
                            + {t.openings.other}
                          </button>
                          <button
                            type="button"
                            aria-label={`toggle-openings-${surface.id}`}
                            onClick={() => toggleOpenings(surface.id)}
                            className={`min-h-11 w-full text-xs px-2 rounded-lg font-semibold transition ${
                              isOpeningsOpen
                                ? 'bg-slate-200 text-slate-800'
                                : 'bg-blue-100 text-blue-800 hover:bg-blue-200'
                            }`}
                          >
                            {isOpeningsOpen ? t.openings.close : t.surfaces.manage_openings}
                          </button>
                        </>
                      )}
                      <button
                        type="button"
                        aria-label={`edit-surface-${surface.id}`}
                        onClick={() => startEdit(surface)}
                        className="min-h-11 w-full text-xs px-2 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                      >
                        {t.common.edit}
                      </button>
                      <button
                        type="button"
                        aria-label={`${surface.is_archived ? 'restore' : 'archive'}-surface-${surface.id}`}
                        onClick={() => void changeArchiveState(surface)}
                        className="min-h-11 w-full text-xs px-2 rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                      >
                        {surface.is_archived ? t.common.restore : t.common.archive}
                      </button>
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
                    <div className="flex gap-2 flex-wrap">
                      <button
                        type="button"
                        aria-label={`edit-surface-${surface.id}`}
                        onClick={() => startEdit(surface)}
                        className="min-h-11 px-3 text-xs rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                      >
                        {t.common.edit}
                      </button>
                      <button
                        type="button"
                        aria-label={`${surface.is_archived ? 'restore' : 'archive'}-surface-${surface.id}`}
                        onClick={() => void changeArchiveState(surface)}
                        className="min-h-11 px-3 text-xs rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                      >
                        {surface.is_archived ? t.common.restore : t.common.archive}
                      </button>
                    </div>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
