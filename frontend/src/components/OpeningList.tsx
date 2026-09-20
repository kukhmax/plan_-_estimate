import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  archiveOpening,
  createOpening,
  fetchOpenings,
  restoreOpening,
  updateOpening,
} from '../api/openings';
import { useI18n } from '../hooks/useI18n';
import { DefaultableOpeningType, useOpeningDefaults } from '../hooks/useOpeningDefaults';
import { RevealWorkPlanEditor } from './RevealWorkPlanEditor';
import {
  OpeningCreatePayload,
  OpeningType,
  OpeningTypeValue,
  OpeningUpdatePayload,
} from '../types/opening';
import { formatMetric } from '../utils/format';
import { localizeApiError } from '../utils/apiErrors';

interface OpeningListProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  initialType?: OpeningTypeValue;
  onOpeningChanged?: () => void;
}

interface OpeningFormState {
  opening_type: OpeningTypeValue;
  name: string;
  width: string;
  height: string;
  quantity: string;
  description: string;
  reveal_enabled: boolean;
  reveal_depth: string;
  reveal_left: boolean;
  reveal_right: boolean;
  reveal_top: boolean;
  reveal_bottom: boolean;
}

const EMPTY_FORM: OpeningFormState = {
  opening_type: 'DOOR',
  name: '',
  width: '',
  height: '',
  quantity: '1',
  description: '',
  reveal_enabled: false,
  reveal_depth: '',
  reveal_left: true,
  reveal_right: true,
  reveal_top: true,
  reveal_bottom: false,
};

export function OpeningList({
  projectId,
  roomId,
  surfaceId,
  initialType,
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
  const [useAsDefault, setUseAsDefault] = useState(false);
  const { defaults, setTypeDefault } = useOpeningDefaults(projectId);
  // Stage 10G.4 — single-open-at-a-time reveal work editor per opening,
  // matching the existing SurfaceWorkPlanEditor toggle convention.
  const [activeRevealWorkOpeningId, setActiveRevealWorkOpeningId] = useState<string | null>(null);
  const toggleRevealWork = (openingId: string) => {
    setActiveRevealWorkOpeningId((current) => (current === openingId ? null : openingId));
  };

  const isDefaultable = (type: OpeningTypeValue): type is DefaultableOpeningType =>
    type === 'DOOR' || type === 'WINDOW';

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
    setUseAsDefault(false);
    setFormError(null);
  };

  const startCreate = (type?: OpeningTypeValue) => {
    setSuccess(null);
    setEditingId(null);
    const resolvedType = type ?? initialType ?? 'DOOR';
    const saved = isDefaultable(resolvedType) ? defaults[resolvedType] : undefined;
    setForm({
      ...EMPTY_FORM,
      opening_type: resolvedType,
      width: saved ? String(saved.width) : '',
      height: saved ? String(saved.height) : '',
    });
    setUseAsDefault(false);
    setFormError(null);
    setShowForm(true);
  };

  useEffect(() => {
    if (initialType) startCreate(initialType);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      reveal_enabled: opening.reveal_enabled ?? false,
      reveal_depth: opening.reveal_depth != null ? String(opening.reveal_depth) : '',
      reveal_left: opening.reveal_left ?? true,
      reveal_right: opening.reveal_right ?? true,
      reveal_top: opening.reveal_top ?? true,
      reveal_bottom: opening.reveal_bottom ?? false,
    });
    setUseAsDefault(false);
    setFormError(null);
    setShowForm(true);
  };

  const handleTypeChange = (type: OpeningTypeValue) => {
    setForm((current) => {
      const saved = isDefaultable(type) ? defaults[type] : undefined;
      return {
        ...current,
        opening_type: type,
        width: saved ? String(saved.width) : '',
        height: saved ? String(saved.height) : '',
        reveal_enabled: type === 'OTHER' ? false : current.reveal_enabled,
      };
    });
  };

  // Preview calculations (UX-only while editing)
  const parsedWidth = parseFloat(form.width.trim());
  const parsedHeight = parseFloat(form.height.trim());
  const parsedQuantity = parseInt(form.quantity.trim(), 10) || 1;
  const hasValidDimensions = !Number.isNaN(parsedWidth) && parsedWidth > 0 &&
                             !Number.isNaN(parsedHeight) && parsedHeight > 0;
  const previewSingleArea = hasValidDimensions ? (parsedWidth * parsedHeight).toFixed(2) : null;
  const previewTotalArea = hasValidDimensions && parsedQuantity >= 1
    ? (parsedWidth * parsedHeight * parsedQuantity).toFixed(2)
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
    if (form.reveal_enabled && form.opening_type !== 'OTHER') {
      const depthNum = parseFloat(form.reveal_depth.trim());
      payload.reveal_enabled = true;
      payload.reveal_depth = Number.isNaN(depthNum) || depthNum <= 0 ? null : depthNum;
      payload.reveal_left = form.reveal_left;
      payload.reveal_right = form.reveal_right;
      payload.reveal_top = form.reveal_top;
      payload.reveal_bottom = form.reveal_bottom;
    } else if (!form.reveal_enabled) {
      payload.reveal_enabled = false;
    }

    try {
      if (editingId) {
        const updatePayload: OpeningUpdatePayload = {
          opening_type: payload.opening_type,
          name: payload.name,
          width: payload.width,
          height: payload.height,
          quantity: payload.quantity,
          description: payload.description,
          reveal_enabled: payload.reveal_enabled,
          reveal_depth: payload.reveal_depth,
          reveal_left: payload.reveal_left,
          reveal_right: payload.reveal_right,
          reveal_top: payload.reveal_top,
          reveal_bottom: payload.reveal_bottom,
        };
        await updateOpening(projectId, roomId, surfaceId, editingId, updatePayload);
        setSuccess(t.openings.updated);
      } else {
        await createOpening(projectId, roomId, surfaceId, payload);
        if (useAsDefault && isDefaultable(payload.opening_type)) {
          setTypeDefault(payload.opening_type, { width: widthNum, height: heightNum });
        }
        setSuccess(t.openings.created);
      }
      closeForm();
      await load();
      onOpeningChanged?.();
    } catch (err) {
      setFormError(localizeApiError(err, t));
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
      setError(localizeApiError(err, t));
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
          onClick={() => startCreate()}
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
                onChange={(e) => handleTypeChange(e.target.value as OpeningTypeValue)}
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
                inputMode="numeric"
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
                inputMode="decimal"
                min="0.001"
                step="any"
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
                inputMode="decimal"
                min="0.001"
                step="any"
                required
                placeholder="2.000"
                value={form.height}
                onChange={(e) => setForm((cur) => ({ ...cur, height: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white"
              />
            </div>
          </div>

          {!editingId && isDefaultable(form.opening_type) && (
            <label className="flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer">
              <input
                aria-label="set-opening-default"
                type="checkbox"
                checked={useAsDefault}
                onChange={(e) => setUseAsDefault(e.target.checked)}
              />
              {t.openings.set_as_default}
            </label>
          )}

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

          {/* Reveal (ościeże) — only for WINDOW and DOOR */}
          {form.opening_type !== 'OTHER' && (
            <div className="pt-1 border-t border-slate-200/60 space-y-2">
              <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
                <input
                  aria-label={`reveal-toggle-${surfaceId}`}
                  type="checkbox"
                  checked={form.reveal_enabled}
                  onChange={(e) => setForm((cur) => ({ ...cur, reveal_enabled: e.target.checked }))}
                />
                {t.reveals.toggle}
              </label>
              {form.reveal_enabled && (
                <div className="space-y-2 pl-1">
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">{t.reveals.depth}</label>
                    <input
                      aria-label="reveal-depth"
                      type="number"
                      inputMode="decimal"
                      min="0.001"
                      step="any"
                      placeholder="0.150"
                      value={form.reveal_depth}
                      onChange={(e) => setForm((cur) => ({ ...cur, reveal_depth: e.target.value }))}
                      className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white"
                    />
                  </div>
                  <div>
                    <span className="block text-xs text-slate-500 mb-1">{t.reveals.sides}</span>
                    <div className="flex flex-wrap gap-3">
                      {([
                        ['reveal_left', t.reveals.side_left],
                        ['reveal_right', t.reveals.side_right],
                        ['reveal_top', t.reveals.side_top],
                        ['reveal_bottom', t.reveals.side_bottom],
                      ] as const).map(([field, label]) => (
                        <label key={field} className="flex items-center gap-1 text-xs text-slate-600 cursor-pointer">
                          <input
                            aria-label={`reveal-${field.replace('reveal_', '')}`}
                            type="checkbox"
                            checked={form[field]}
                            onChange={(e) => setForm((cur) => ({ ...cur, [field]: e.target.checked }))}
                          />
                          {label}
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Secondary optional fields: Name & Description */}
          <div className="pt-1 border-t border-slate-200/60 space-y-1.5">
            <span className="block text-[11px] text-slate-400 font-medium">
              {t.openings.optional_details}
            </span>
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
              className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs bg-white min-h-12"
            />
          </div>

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
              className="bg-slate-50 border border-slate-200 rounded-xl p-2.5"
            >
              <div className="flex items-start justify-between gap-2">
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

                {opening.reveal_enabled && opening.reveal_total_length != null && (
                  <div className="text-slate-500 mt-0.5 text-[11px]">
                    {t.reveals.summary_title}:{' '}
                    <strong className="text-slate-700">{formatMetric(opening.reveal_total_length)} {t.pricebook.units.LM}</strong>
                    {' · '}
                    <strong className="text-slate-700">{formatMetric(opening.reveal_total_area)} {t.common.unit_m2}</strong>
                  </div>
                )}
              </div>

              <div className="flex items-center gap-1.5 flex-wrap justify-end flex-shrink-0">
                <button
                  type="button"
                  aria-label={`edit-opening-${opening.id}`}
                  onClick={() => startEdit(opening)}
                  className="text-xs px-2.5 py-1.5 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                >
                  {t.common.edit}
                </button>
                <button
                  type="button"
                  aria-label={`${opening.is_archived ? 'restore' : 'archive'}-opening-${opening.id}`}
                  onClick={() => void changeArchiveState(opening)}
                  className="text-xs px-2.5 py-1.5 rounded-lg bg-slate-200 text-slate-700 font-medium hover:bg-slate-300 transition"
                >
                  {opening.is_archived ? t.common.restore : t.common.archive}
                </button>
              </div>
              </div>

              {/* Stage 10G.4 — reveal work planning per opening; never shown
                  when reveal is disabled, and never silently enables it. */}
              {opening.reveal_enabled && (
                <div className="pt-2 mt-2 border-t border-slate-200">
                  <button
                    type="button"
                    aria-label={`reveal-work-toggle-${opening.id}`}
                    aria-expanded={activeRevealWorkOpeningId === opening.id}
                    aria-controls={`reveal-work-editor-${opening.id}`}
                    onClick={() => toggleRevealWork(opening.id)}
                    className="w-full min-h-[44px] px-3 py-2 text-xs font-medium rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition text-left"
                  >
                    {t.reveals.work_section_title}
                  </button>

                  {activeRevealWorkOpeningId === opening.id && (
                    <RevealWorkPlanEditor
                      projectId={projectId}
                      roomId={roomId}
                      surfaceId={surfaceId}
                      openingId={opening.id}
                      openingLabel={`${typeLabel(opening.opening_type)}${opening.name ? ` (${opening.name})` : ''}`}
                      revealTotalLength={opening.reveal_total_length}
                      revealTotalArea={opening.reveal_total_area}
                      onClose={() => setActiveRevealWorkOpeningId(null)}
                    />
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
