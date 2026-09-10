import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  archiveOpening,
  createOpening,
  fetchOpenings,
  restoreOpening,
  updateOpening,
} from '../api/openings';
import { useI18n } from '../hooks/useI18n';
import {
  OpeningCreatePayload,
  OpeningType,
  OpeningTypeValue,
  OpeningUpdatePayload,
} from '../types/opening';
import { formatMetric } from '../utils/format';

interface OpeningListProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  onOpeningChanged?: () => void;
}

interface OpeningFormState {
  opening_type: OpeningTypeValue;
  name: string;
  width: string;
  height: string;
  quantity: string;
  description: string;
}

const EMPTY_FORM: OpeningFormState = {
  opening_type: 'DOOR',
  name: '',
  width: '',
  height: '',
  quantity: '1',
  description: '',
};

export function OpeningList({
  projectId,
  roomId,
  surfaceId,
  onOpeningChanged,
}: OpeningListProps) {
  const { t } = useI18n();
  const [openings, setOpenings] = useState<OpeningType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<OpeningFormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOpenings(projectId, roomId, surfaceId, includeArchived);
      setOpenings(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.openings.error);
    } finally {
      setLoading(false);
    }
  }, [includeArchived, projectId, roomId, surfaceId, t.openings.error]);

  useEffect(() => {
    void load();
  }, [load]);

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

  const startEdit = (opening: OpeningType) => {
    setSuccess(null);
    setEditingId(opening.id);
    setForm({
      opening_type: opening.opening_type,
      name: opening.name ?? '',
      width: opening.width !== null ? String(opening.width) : '',
      height: opening.height !== null ? String(opening.height) : '',
      quantity: String(opening.quantity ?? 1),
      description: opening.description ?? '',
    });
    setFormError(null);
    setShowForm(true);
  };

  // Preview calculations (UX-only while editing)
  const parsedWidth = parseFloat(form.width.trim());
  const parsedHeight = parseFloat(form.height.trim());
  const parsedQuantity = parseInt(form.quantity.trim(), 10) || 1;
  const hasValidDimensions = !Number.isNaN(parsedWidth) && parsedWidth > 0 &&
                             !Number.isNaN(parsedHeight) && parsedHeight > 0;
  const previewSingleArea = hasValidDimensions ? (parsedWidth * parsedHeight).toFixed(3) : null;
  const previewTotalArea = hasValidDimensions && parsedQuantity >= 1
    ? (parsedWidth * parsedHeight * parsedQuantity).toFixed(3)
    : null;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);

    const widthNum = parseFloat(form.width.trim());
    const heightNum = parseFloat(form.height.trim());
    const quantityNum = parseInt(form.quantity.trim(), 10) || 1;

    if (Number.isNaN(widthNum) || widthNum <= 0 || Number.isNaN(heightNum) || heightNum <= 0) {
      setFormError(t.openings.error);
      setSaving(false);
      return;
    }

    const payload: OpeningCreatePayload = {
      opening_type: form.opening_type,
      name: form.name.trim() || null,
      width: widthNum,
      height: heightNum,
      quantity: quantityNum,
      description: form.description.trim() || null,
    };

    try {
      if (editingId) {
        const updatePayload: OpeningUpdatePayload = {
          opening_type: payload.opening_type,
          name: payload.name,
          width: payload.width,
          height: payload.height,
          quantity: payload.quantity,
          description: payload.description,
        };
        await updateOpening(projectId, roomId, surfaceId, editingId, updatePayload);
        setSuccess(t.openings.updated);
      } else {
        await createOpening(projectId, roomId, surfaceId, payload);
        setSuccess(t.openings.created);
      }
      closeForm();
      await load();
      onOpeningChanged?.();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t.openings.error);
    } finally {
      setSaving(false);
    }
  };

  const changeArchiveState = async (opening: OpeningType) => {
    setError(null);
    setSuccess(null);
    try {
      if (opening.is_archived) {
        await restoreOpening(projectId, roomId, surfaceId, opening.id);
        setSuccess(t.openings.restored);
      } else {
        await archiveOpening(projectId, roomId, surfaceId, opening.id);
        setSuccess(t.openings.archived);
      }
      await load();
      onOpeningChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.openings.error);
    }
  };

  const typeLabel = (type: OpeningTypeValue) => {
    const labels: Record<OpeningTypeValue, string> = {
      DOOR: t.openings.door,
      WINDOW: t.openings.window,
      OTHER: t.openings.other,
    };
    return labels[type];
  };

  return (
    <div aria-label={`openings-container-${surfaceId}`} className="mt-3 pt-3 border-t border-slate-100">
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <h5 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          {t.openings.title}
        </h5>
        <button
          type="button"
          aria-label={`add-opening-${surfaceId}`}
          onClick={startCreate}
          className="text-xs px-2.5 py-1 bg-blue-50 text-blue-700 font-semibold rounded-lg hover:bg-blue-100 transition"
        >
          + {t.openings.add}
        </button>
      </div>

      <label className="flex items-center gap-1.5 text-xs text-slate-500 mb-2 cursor-pointer">
        <input
          aria-label={`show-archived-openings-${surfaceId}`}
          type="checkbox"
          checked={includeArchived}
          onChange={(e) => setIncludeArchived(e.target.checked)}
        />
        {t.common.show_archived}
      </label>

      {showForm && (
        <form
          aria-label={`opening-form-${surfaceId}`}
          onSubmit={handleSubmit}
          className="bg-slate-50 border border-slate-200 rounded-xl p-3 mb-3 space-y-2.5"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-900">
              {editingId ? t.openings.edit : t.openings.add}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t.openings.type}</label>
              <select
                aria-label="opening-type"
                value={form.opening_type}
                onChange={(e) =>
                  setForm((cur) => ({ ...cur, opening_type: e.target.value as OpeningTypeValue }))
                }
                className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white"
              >
                {(['DOOR', 'WINDOW', 'OTHER'] as const).map((type) => (
                  <option key={type} value={type}>
                    {typeLabel(type)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs text-slate-500 mb-1">{t.openings.quantity}</label>
              <input
                aria-label="opening-quantity"
                type="number"
                min="1"
                step="1"
                required
                value={form.quantity}
                onChange={(e) => setForm((cur) => ({ ...cur, quantity: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t.openings.width}</label>
              <input
                aria-label="opening-width"
                type="number"
                min="0.001"
                step="0.001"
                required
                placeholder="0.900"
                value={form.width}
                onChange={(e) => setForm((cur) => ({ ...cur, width: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t.openings.height}</label>
              <input
                aria-label="opening-height"
                type="number"
                min="0.001"
                step="0.001"
                required
                placeholder="2.000"
                value={form.height}
                onChange={(e) => setForm((cur) => ({ ...cur, height: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white"
              />
            </div>
          </div>

          {previewSingleArea !== null && (
            <div
              aria-label="opening-preview-area"
              className="bg-blue-50 border border-blue-100 rounded-lg p-2 text-xs text-blue-800 space-y-0.5"
            >
              <div className="flex justify-between">
                <span>{t.openings.single_area}:</span>
                <span className="font-semibold">{previewSingleArea} {t.common.unit_m2}</span>
              </div>
              {parsedQuantity > 1 && previewTotalArea !== null && (
                <div className="flex justify-between">
                  <span>{t.openings.total_area} ({parsedQuantity} {t.common.unit_pcs}):</span>
                  <span className="font-bold text-blue-900">{previewTotalArea} {t.common.unit_m2}</span>
                </div>
              )}
            </div>
          )}

          <input
            aria-label="opening-name"
            maxLength={255}
            placeholder={t.openings.name}
            value={form.name}
            onChange={(e) => setForm((cur) => ({ ...cur, name: e.target.value }))}
            className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white"
          />

          <textarea
            aria-label="opening-description"
            maxLength={4096}
            placeholder={t.openings.description}
            value={form.description}
            onChange={(e) => setForm((cur) => ({ ...cur, description: e.target.value }))}
            className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white min-h-16"
          />

          {formError && (
            <p role="alert" className="text-xs text-red-600 font-medium bg-red-50 p-2 rounded-lg border border-red-100">
              {formError}
            </p>
          )}

          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              onClick={closeForm}
              className="px-2.5 py-1 text-xs rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100"
            >
              {t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-3 py-1 text-xs bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
            >
              {saving ? t.common.saving : t.common.save}
            </button>
          </div>
        </form>
      )}

      {success && <p role="status" className="text-xs text-emerald-700 mb-2">{success}</p>}
      {loading && <p className="text-xs text-slate-400 py-2 text-center">{t.openings.loading}</p>}
      {!loading && error && <p role="alert" className="text-xs text-red-600 py-2">{error}</p>}
      {!loading && !error && openings.length === 0 && (
        <p aria-label={`no-openings-${surfaceId}`} className="text-xs text-slate-400 py-2 italic text-center">
          {t.openings.empty}
        </p>
      )}

      {!loading && !error && openings.length > 0 && (
        <ul aria-label={`openings-list-${surfaceId}`} className="space-y-1.5">
          {openings.map((opening) => (
            <li
              key={opening.id}
              aria-label={`opening-item-${opening.id}`}
              className="bg-slate-50 border border-slate-200 rounded-xl p-2.5 flex items-start justify-between gap-2"
            >
              <div className="min-w-0 text-xs">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="font-semibold text-slate-800">
                    {typeLabel(opening.opening_type)}
                  </span>
                  {opening.name && (
                    <span className="text-slate-600 font-medium">({opening.name})</span>
                  )}
                  {opening.quantity > 1 && (
                    <span className="px-1.5 py-0.2 rounded-full bg-slate-200 text-slate-700 font-bold">
                      ×{opening.quantity}
                    </span>
                  )}
                  {opening.is_archived && (
                    <span className="px-1.5 py-0.2 rounded-full bg-orange-100 text-orange-700 font-medium">
                      {t.common.archived_badge}
                    </span>
                  )}
                </div>

                <div className="text-slate-500 mt-1 space-x-2">
                  <span>
                    {formatMetric(opening.width)} × {formatMetric(opening.height)} {t.common.unit_m}
                  </span>
                  <span>•</span>
                  <span>
                    {t.openings.total_area}: <strong className="text-slate-800">{formatMetric(opening.total_area)} {t.common.unit_m2}</strong>
                  </span>
                </div>

                {opening.description && (
                  <p className="text-slate-400 text-[11px] mt-0.5">{opening.description}</p>
                )}
              </div>

              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  type="button"
                  aria-label={`edit-opening-${opening.id}`}
                  onClick={() => startEdit(opening)}
                  className="text-[11px] px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-medium hover:bg-blue-100"
                >
                  {t.common.edit}
                </button>
                <button
                  type="button"
                  aria-label={`${opening.is_archived ? 'restore' : 'archive'}-opening-${opening.id}`}
                  onClick={() => void changeArchiveState(opening)}
                  className="text-[11px] px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-medium hover:bg-slate-300"
                >
                  {opening.is_archived ? t.common.restore : t.common.archive}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
