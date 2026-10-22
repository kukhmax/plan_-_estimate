import { FormEvent, ReactNode, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { formatMetric } from '../utils/format';
import { DimensionInput } from './DimensionInput';
import { Ico } from './Ico';

interface SurfaceDimensionsProps {
  surfaceId: string;
  /** The saved size in metres; absent for a surface that has none yet. */
  width: string | number | null | undefined;
  height: string | number | null | undefined;
  /** An archived surface is not edited. */
  readOnly?: boolean;
  /** Saves the new size (metres); a rejection carries the message to show. */
  onSave: (width: number, height: number) => Promise<void>;
  /** A second quiet action shown right after "Edytuj" (the wall card puts "Duplikuj ścianę" here, in sight). */
  extraAction?: ReactNode;
}

const asText = (value: string | number | null | undefined) => (value === null || value === undefined ? '' : String(value));

/**
 * The size of a wall (or another surface) on its card, with a one-tap way to change it (Stage 19, owner request): the owner measures, adds
 * the wall, and the next thing is often to correct the size — it must not take opening "Opcje" and a form at the top of a long list.
 * Closed: "Wymiary: 1.95 × 2.60 m  [✏️ Edytuj]". Open: the two fields (centimetres, as everywhere) with Zapisz / Anuluj right there.
 */
export function SurfaceDimensions({ surfaceId, width, height, readOnly = false, onSave, extraAction }: SurfaceDimensionsProps) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [draftWidth, setDraftWidth] = useState('');
  const [draftHeight, setDraftHeight] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const has = asText(width) !== '' && asText(height) !== '';

  const open = () => {
    setDraftWidth(asText(width));
    setDraftHeight(asText(height));
    setError(null);
    setEditing(true);
  };
  const close = () => {
    setEditing(false);
    setError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const w = parseFloat(draftWidth);
    const h = parseFloat(draftHeight);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
      setError(t.surfaces.error);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(w, h);
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t.surfaces.error);
    } finally {
      setSaving(false);
    }
  };

  const secondary =
    'min-h-11 px-3 py-1 text-xs rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition';

  if (editing) {
    return (
      <form aria-label={`dimensions-form-${surfaceId}`} onSubmit={(event) => void submit(event)} className="space-y-2 rounded-xl border border-blue-200 pe-surface p-2.5">
        <div className="grid grid-cols-2 gap-2">
          <div className="min-w-0">
            <label className="block text-[11px] text-slate-500 mb-1">{t.surfaces.width}</label>
            <DimensionInput
              aria-label={`dimensions-width-${surfaceId}`}
              placeholder="500"
              value={draftWidth}
              onValueChange={setDraftWidth}
              className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div className="min-w-0">
            <label className="block text-[11px] text-slate-500 mb-1">{t.surfaces.height}</label>
            <DimensionInput
              aria-label={`dimensions-height-${surfaceId}`}
              placeholder="270"
              value={draftHeight}
              onValueChange={setDraftHeight}
              className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
        </div>
        {error && <p role="alert" className="text-xs text-red-600 font-medium break-words">{error}</p>}
        <div className="flex gap-2 flex-wrap">
          <button type="submit" disabled={saving} aria-label={`dimensions-save-${surfaceId}`} className="min-h-11 px-3 py-1 text-xs bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition disabled:opacity-50">
            <Ico>💾</Ico>{saving ? t.common.saving : t.common.save}
          </button>
          <button type="button" disabled={saving} aria-label={`dimensions-cancel-${surfaceId}`} onClick={close} className="min-h-11 px-3 py-1 text-xs rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50">
            <Ico>✖️</Ico>{t.common.cancel}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
      {has && (
        <p className="min-w-0 break-words">
          <span>{t.surfaces.dimensions}: </span>
          <strong className="text-slate-900 font-semibold">
            {formatMetric(width)} × {formatMetric(height)} {t.common.unit_m}
          </strong>
        </p>
      )}
      {!readOnly && (
        <button type="button" aria-label={`edit-dimensions-${surfaceId}`} onClick={open} className={secondary}>
          <Ico>✏️</Ico>
          {has ? t.common.edit : t.surfaces.add_dimensions}
        </button>
      )}
      {extraAction}
    </div>
  );
}
