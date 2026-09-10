import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  archiveSurface,
  createSurface,
  fetchSurfaces,
  restoreSurface,
  updateSurface,
} from '../api/surfaces';
import { useI18n } from '../hooks/useI18n';
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
  onMeasurementChanged?: () => void;
}

interface SurfaceFormState {
  name: string;
  surface_type: SurfaceTypeValue;
  description: string;
  width: string;
  height: string;
}

const EMPTY_FORM: SurfaceFormState = {
  name: '',
  surface_type: 'WALL',
  description: '',
  width: '',
  height: '',
};

export function SurfaceList({ projectId, roomId, onMeasurementChanged }: SurfaceListProps) {
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
  };

  const handleOpeningChanged = () => {
    void load();
    onMeasurementChanged?.();
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const startCreate = () => {
    setSuccess(null);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setShowForm(true);
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
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="text-lg font-bold text-slate-900">{t.surfaces.title}</h3>
        <button
          type="button"
          aria-label="add-surface"
          onClick={startCreate}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
        >
          {t.surfaces.add}
        </button>
      </div>

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
                step="0.001"
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
                step="0.001"
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
                className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-slate-900 text-sm">{surface.name}</span>
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
                      <div className="mt-2 text-xs space-y-1.5">
                        <div className="text-slate-600">
                          <span>{t.surfaces.dimensions}: </span>
                          <strong className="text-slate-900 font-semibold">
                            {formatMetric(surface.width)} × {formatMetric(surface.height)} {t.common.unit_m}
                          </strong>
                        </div>

                        {isWall ? (
                          <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-2.5 text-xs">
                            <div className="flex items-center justify-between gap-1.5 flex-wrap">
                              <div className="space-y-0.5">
                                <span className="text-[11px] text-slate-500 block">{t.surfaces.gross_area}</span>
                                <strong className="text-slate-800 text-xs font-semibold">
                                  {formatMetric(surface.gross_area)} {t.common.unit_m2}
                                </strong>
                              </div>
                              <span className="text-slate-300 font-bold self-center">−</span>
                              <div className="space-y-0.5">
                                <span className="text-[11px] text-slate-500 block">{t.surfaces.deduction_area}</span>
                                <strong className="text-slate-700 text-xs font-semibold">
                                  {formatMetric(surface.deduction_area ?? '0.000')} {t.common.unit_m2}
                                </strong>
                              </div>
                              <span className="text-slate-300 font-bold self-center">=</span>
                              <div className="space-y-0.5 bg-emerald-50 border border-emerald-200/60 rounded-lg px-2 py-1">
                                <span className="text-[11px] text-emerald-800 font-medium block">{t.surfaces.net_area}</span>
                                <strong className="text-emerald-700 text-xs sm:text-sm font-bold">
                                  {formatMetric(surface.net_area ?? surface.gross_area)} {t.common.unit_m2}
                                </strong>
                              </div>
                            </div>
                          </div>
                        ) : (
                          surface.gross_area && (
                            <p className="text-xs text-slate-600">
                              <span>{t.surfaces.gross_area}: </span>
                              <strong className="text-slate-800">{formatMetric(surface.gross_area)} {t.common.unit_m2}</strong>
                            </p>
                          )
                        )}
                      </div>
                    )}

                    {isWall && !hasDimensions && (
                      <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-2 py-1 mt-1.5">
                        {t.surfaces.requires_dimensions}
                      </p>
                    )}

                    {surface.description && <p className="text-xs text-slate-500 mt-1.5">{surface.description}</p>}
                  </div>

                  <div className="flex gap-1.5 flex-wrap justify-end flex-shrink-0">
                    {isWall && hasDimensions && (
                      <button
                        type="button"
                        aria-label={`toggle-openings-${surface.id}`}
                        onClick={() => toggleOpenings(surface.id)}
                        className={`text-xs px-2.5 py-1 rounded-lg font-medium transition ${
                          isOpeningsOpen
                            ? 'bg-slate-200 text-slate-800'
                            : 'bg-blue-100 text-blue-800 hover:bg-blue-200'
                        }`}
                      >
                        {isOpeningsOpen ? t.openings.close : t.surfaces.manage_openings}
                      </button>
                    )}
                    <button
                      type="button"
                      aria-label={`edit-surface-${surface.id}`}
                      onClick={() => startEdit(surface)}
                      className="text-xs px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                    >
                      {t.common.edit}
                    </button>
                    <button
                      type="button"
                      aria-label={`${surface.is_archived ? 'restore' : 'archive'}-surface-${surface.id}`}
                      onClick={() => void changeArchiveState(surface)}
                      className="text-xs px-2.5 py-1 rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                    >
                      {surface.is_archived ? t.common.restore : t.common.archive}
                    </button>
                  </div>
                </div>

                {isWall && hasDimensions && isOpeningsOpen && (
                  <OpeningList
                    projectId={projectId}
                    roomId={roomId}
                    surfaceId={surface.id}
                    onOpeningChanged={handleOpeningChanged}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
