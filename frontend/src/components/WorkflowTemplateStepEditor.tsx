import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchPriceItems } from '../api/priceItems';
import {
  classifyTemplateManagementError,
  fetchWorkflowTemplate,
  replaceWorkflowTemplateSteps,
} from '../api/workflowTemplates';
import { useI18n } from '../hooks/useI18n';
import { PriceItem } from '../types/priceItem';
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { WorkflowTemplateRead } from '../types/workflowTemplate';
import { localizeApiError } from '../utils/apiErrors';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice } from '../utils/priceFormat';

/**
 * Stage 13F.5 — technological step editor for ONE workflow template.
 *
 * An explicit draft: nothing is persisted until "Zapisz kroki", which sends
 * the complete ordered step list (PUT …/steps) together with the ordered step
 * ids the editor was opened with (`expected_step_ids`, 13F.2). Any concurrent
 * change on the server is a 409: the draft is kept, nothing is overwritten,
 * and the owner may explicitly reload the server version. Template edits never
 * touch materialized WorkPlans, Estimates or application history (server rule).
 *
 * Each draft row is an independent occurrence: the same PriceItem may appear
 * several times. Template step ids are NOT WorkPlan occurrence keys.
 */

interface DraftStep {
  /** Local identity only (existing step id or a new local id). */
  key: string;
  priceItemId: string;
  priceItem: SurfacePriceItemSummaryRead | null;
  isOptional: boolean;
  note: string;
  /** Raw input; empty = no technological break. */
  wait: string;
  /** Stored note + derived key of the server step (for display only). */
  originalNote: string | null;
  noteKey: string | null;
}

interface WorkflowTemplateStepEditorProps {
  template: WorkflowTemplateRead;
  templateName: string;
  onSaved: (template: WorkflowTemplateRead) => void;
  onClose: () => void;
}

let newKeySeq = 0;

function toDraft(tpl: WorkflowTemplateRead): DraftStep[] {
  return tpl.steps.map((step) => ({
    key: step.id,
    priceItemId: step.price_item_id,
    priceItem: step.price_item,
    isOptional: step.is_optional,
    note: step.note ?? '',
    wait: step.wait_after_hours === null ? '' : String(step.wait_after_hours),
    originalNote: step.note,
    noteKey: step.note_key ?? null,
  }));
}

/** Whole hours >= 1, or empty (no break). Anything else is invalid. */
function parseWait(raw: string): number | null | 'invalid' {
  const value = raw.trim();
  if (value === '') return null;
  if (!/^\d+$/.test(value)) return 'invalid';
  const hours = Number(value);
  return hours >= 1 ? hours : 'invalid';
}

function signature(steps: DraftStep[]): string {
  return JSON.stringify(steps.map((s) => [s.priceItemId, s.isOptional, s.note.trim(), s.wait.trim()]));
}

export function WorkflowTemplateStepEditor({ template, templateName, onSaved, onClose }: WorkflowTemplateStepEditorProps) {
  const { t } = useI18n();
  const [base, setBase] = useState<WorkflowTemplateRead>(template);
  const [draft, setDraft] = useState<DraftStep[]>(() => toDraft(template));
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [confirmRemoveKey, setConfirmRemoveKey] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState<{ text: string; detail: string | null; stale: boolean } | null>(null);
  const inFlight = useRef(false);

  // The precondition: exactly the ordered server step ids this draft is based on.
  const expectedStepIds = useMemo(() => base.steps.map((s) => s.id), [base]);
  const dirty = signature(draft) !== signature(toDraft(base));
  const invalidWait = draft.some((s) => parseWait(s.wait) === 'invalid');

  const itemName = (item: SurfacePriceItemSummaryRead | null): string => {
    if (!item) return t.work_plan.unavailable_item;
    if (item.display_name) return item.display_name;
    if (item.name_key) {
      const localized = resolveKey(t, item.name_key);
      if (localized !== item.name_key) return localized;
    }
    return item.code;
  };

  /** Canonical localization applies only while the note is the untouched stored note. */
  const shownNote = (step: DraftStep): string => {
    if (step.noteKey && step.note === (step.originalNote ?? '')) {
      const localized = resolveKey(t, step.noteKey);
      if (localized !== step.noteKey) return localized;
    }
    return step.note.trim();
  };

  const waitHint = (raw: string): string | null => {
    const hours = parseWait(raw);
    if (typeof hours !== 'number' || hours % 24 !== 0) return null;
    const days = hours / 24;
    return t.processes.wait_days_hint.replace('{hours}', String(hours)).replace('{days}', String(days));
  };

  const update = (key: string, patch: Partial<DraftStep>) => {
    setDraft((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));
    setError((prev) => (prev?.stale ? prev : null));
  };

  const move = (index: number, delta: -1 | 1) => {
    setDraft((prev) => {
      const next = [...prev];
      const [row] = next.splice(index, 1);
      next.splice(index + delta, 0, row);
      return next;
    });
  };

  const remove = (key: string) => {
    setDraft((prev) => prev.filter((s) => s.key !== key));
    setConfirmRemoveKey(null);
    setOpenKey(null);
  };

  const addItem = (item: PriceItem) => {
    newKeySeq += 1;
    const key = `new-${newKeySeq}`;
    setDraft((prev) => [
      ...prev,
      {
        key,
        priceItemId: item.id,
        priceItem: {
          id: item.id, code: item.code, name_key: item.name_key, display_name: item.display_name,
          category: item.category, unit: item.unit, price_scope: item.price_scope, price: item.price,
          currency: item.currency, is_archived: item.is_archived, quality_level: item.quality_level,
        },
        isOptional: false,
        note: '',
        wait: '',
        originalNote: null,
        noteKey: null,
      },
    ]);
    setPickerOpen(false);
    setOpenKey(key);
  };

  const errorFor = (err: unknown) => {
    const kind = classifyTemplateManagementError(err);
    const text = {
      network: t.processes.error_network,
      stale_steps: t.processes.steps_stale,
      price_item_not_found: t.processes.steps_item_missing,
      not_found: t.processes.error_not_found,
      name_required: t.processes.steps_save_error,
      quality_scale: t.processes.steps_save_error,
      archived_item: t.processes.steps_archived_rejected,
      validation: t.processes.steps_save_error,
      other: t.processes.steps_save_error,
    }[kind];
    return {
      text,
      detail: kind === 'validation' || kind === 'other' ? localizeApiError(err, t) : null,
      stale: kind === 'stale_steps',
    };
  };

  const save = async () => {
    if (inFlight.current || !dirty || invalidWait) return;
    inFlight.current = true;
    setSaving(true);
    setError(null);
    try {
      const saved = await replaceWorkflowTemplateSteps(
        base.id,
        draft.map((s) => ({
          price_item_id: s.priceItemId,
          is_optional: s.isOptional,
          note: s.note.trim() || null,
          wait_after_hours: parseWait(s.wait) as number | null,
        })),
        expectedStepIds,
      );
      // Canonical server state (new step ids, derived note keys).
      onSaved(await fetchWorkflowTemplate(saved.id));
    } catch (err) {
      setError(errorFor(err)); // the draft stays intact; never retried automatically
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  /** Explicit owner action after a 409: replace the draft with the server version. */
  const reloadServer = async () => {
    setReloading(true);
    try {
      const fresh = await fetchWorkflowTemplate(base.id);
      setBase(fresh);
      setDraft(toDraft(fresh));
      setOpenKey(null);
      setConfirmRemoveKey(null);
      setError(null);
    } catch (err) {
      setError({ ...errorFor(err), stale: true });
    } finally {
      setReloading(false);
    }
  };

  const requestClose = () => {
    if (dirty && !saving) setConfirmDiscard(true);
    else onClose();
  };

  const btn = 'min-h-11 px-3 rounded-xl text-sm font-semibold disabled:opacity-50';
  const secondary = `${btn} border border-slate-300 bg-white text-slate-700`;

  return (
    <section aria-label={`process-steps-editor-${base.id}`} className="space-y-3">
      <button type="button" aria-label="steps-editor-back" onClick={requestClose} disabled={saving}
        className="w-full min-h-11 px-3 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 text-left">
        ← {templateName}
      </button>
      <div className="space-y-1">
        <h3 className="text-base font-bold text-slate-900 break-words">{t.processes.steps_editor_title}</h3>
        <p className="text-xs text-slate-500 break-words">{t.processes.steps_editor_info}</p>
        <p aria-label="steps-editor-count" className="text-sm font-medium text-slate-700">
          {t.work_plan.tpl_steps_count.replace('{count}', String(draft.length))}
        </p>
      </div>

      {draft.length === 0 && (
        <p aria-label="steps-editor-empty" className="rounded-xl bg-amber-50 text-amber-900 p-3 text-sm break-words">
          {t.processes.steps_editor_empty}
        </p>
      )}

      <ol aria-label="steps-editor-list" className="space-y-2">
        {draft.map((step, index) => {
          const item = step.priceItem;
          const archived = !item || item.is_archived;
          const note = shownNote(step);
          const wait = parseWait(step.wait);
          const isOpen = openKey === step.key;
          return (
            <li key={step.key} aria-label={`steps-editor-row-${index}`} className="rounded-2xl border border-slate-200 bg-white p-3 space-y-2">
              <div className="flex items-start gap-2">
                <span className="shrink-0 text-sm font-semibold text-slate-400">{index + 1}.</span>
                <span className="flex-1 min-w-0 text-sm font-medium text-slate-900 break-words">{itemName(item)}</span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-xs pl-6">
                <span className={`px-2 py-0.5 rounded-full font-medium ${step.isOptional ? 'bg-slate-100 text-slate-700' : 'bg-blue-50 text-blue-700'}`}>
                  {step.isOptional ? t.work_plan.tpl_optional : t.work_plan.tpl_required}
                </span>
                {item && <span className="text-slate-500">{t.pricebook.units[item.unit]}</span>}
                {typeof wait === 'number' && (
                  <span className="text-slate-500">{t.work_plan.tpl_wait.replace('{hours}', String(wait))}</span>
                )}
                {archived && <span className="px-2 py-0.5 rounded-full bg-red-50 text-red-700 break-words">{t.work_plan.tpl_archived_item}</span>}
                {!archived && item?.price === null && (
                  <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 break-words">{t.processes.no_price}</span>
                )}
              </div>
              {note && <p aria-label={`steps-editor-note-${index}`} className="text-xs text-slate-500 break-words pl-6">{note}</p>}

              <button type="button" aria-label={`steps-editor-options-${index}`} aria-expanded={isOpen}
                onClick={() => { setOpenKey(isOpen ? null : step.key); setConfirmRemoveKey(null); }}
                className={`w-full ${btn} bg-slate-100 text-slate-800`}>
                {isOpen ? t.surfaces.hide_options : t.surfaces.options}
              </button>

              {isOpen && (
                <div className="space-y-3 pt-1">
                  <div role="group" aria-label={`steps-editor-kind-${index}`} className="grid grid-cols-2 gap-2">
                    {([false, true] as const).map((optional) => (
                      <button key={String(optional)} type="button" aria-pressed={step.isOptional === optional}
                        aria-label={`steps-editor-${optional ? 'optional' : 'required'}-${index}`}
                        onClick={() => update(step.key, { isOptional: optional })}
                        className={`min-h-11 px-2 rounded-xl text-xs font-semibold min-w-0 break-words ${step.isOptional === optional ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700'}`}>
                        {optional ? t.work_plan.tpl_optional : t.work_plan.tpl_required}
                      </button>
                    ))}
                  </div>
                  <label className="block space-y-1">
                    <span className="block text-xs font-medium text-slate-600">{t.processes.step_note_label}</span>
                    <textarea aria-label={`steps-editor-note-input-${index}`} value={step.note} rows={3} maxLength={4000}
                      onChange={(e) => update(step.key, { note: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-300 text-sm" />
                    {step.noteKey && step.note === (step.originalNote ?? '') && (
                      <span className="block text-xs text-slate-500 break-words">{t.processes.step_note_builtin_hint}</span>
                    )}
                  </label>
                  <label className="block space-y-1">
                    <span className="block text-xs font-medium text-slate-600">{t.processes.step_wait_label}</span>
                    <input aria-label={`steps-editor-wait-${index}`} value={step.wait} inputMode="numeric"
                      onChange={(e) => update(step.key, { wait: e.target.value })}
                      placeholder={t.processes.step_wait_placeholder}
                      className="w-full min-h-11 px-3 rounded-xl border border-slate-300 text-sm" />
                    {wait === 'invalid' ? (
                      <span role="alert" className="block text-xs text-red-600">{t.processes.step_wait_invalid}</span>
                    ) : (
                      waitHint(step.wait) && <span className="block text-xs text-slate-500">{waitHint(step.wait)}</span>
                    )}
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button type="button" aria-label={`steps-editor-up-${index}`} disabled={index === 0}
                      onClick={() => move(index, -1)} className={secondary}>↑ {t.processes.move_up}</button>
                    <button type="button" aria-label={`steps-editor-down-${index}`} disabled={index === draft.length - 1}
                      onClick={() => move(index, 1)} className={secondary}>↓ {t.processes.move_down}</button>
                  </div>
                  {confirmRemoveKey === step.key ? (
                    <div role="alertdialog" aria-label={`steps-editor-remove-confirm-${index}`} className="rounded-xl border border-red-200 bg-red-50 p-3 space-y-2">
                      <p className="text-xs text-red-800 break-words">{t.processes.remove_step_confirm}</p>
                      <div className="grid grid-cols-2 gap-2">
                        <button type="button" onClick={() => setConfirmRemoveKey(null)} className={secondary}>{t.common.cancel}</button>
                        <button type="button" aria-label={`steps-editor-remove-yes-${index}`} onClick={() => remove(step.key)}
                          className={`${btn} bg-red-600 text-white`}>{t.processes.remove_step}</button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" aria-label={`steps-editor-remove-${index}`}
                      onClick={() => (step.key.startsWith('new-') ? remove(step.key) : setConfirmRemoveKey(step.key))}
                      className={`w-full ${btn} border border-red-300 bg-white text-red-700`}>
                      {t.processes.remove_step}
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {pickerOpen ? (
        <StepItemPicker onPick={addItem} onCancel={() => setPickerOpen(false)} />
      ) : (
        <button type="button" aria-label="steps-editor-add" onClick={() => setPickerOpen(true)} disabled={saving}
          className={`w-full ${btn} border border-blue-600 bg-white text-blue-700`}>
          + {t.processes.add_step}
        </button>
      )}

      {error && (
        <div role="alert" aria-label="steps-editor-error" className="rounded-xl border border-red-200 bg-red-50 p-3 space-y-2">
          <p className="text-sm font-semibold text-red-700 break-words">{error.text}</p>
          {error.detail && error.detail !== error.text && <p className="text-xs text-red-700 break-words">{error.detail}</p>}
          {error.stale && (
            <button type="button" aria-label="steps-editor-reload" onClick={() => void reloadServer()} disabled={reloading}
              className={`w-full ${secondary}`}>
              {t.processes.steps_reload}
            </button>
          )}
        </div>
      )}

      {confirmDiscard ? (
        <div role="alertdialog" aria-label="steps-editor-discard-confirm" className="rounded-2xl border border-amber-300 bg-amber-50 p-3 space-y-2">
          <p className="text-sm font-semibold text-amber-900 break-words">{t.processes.discard_title}</p>
          <div className="grid grid-cols-2 gap-2">
            <button type="button" onClick={() => setConfirmDiscard(false)} className={secondary}>{t.processes.keep_editing}</button>
            <button type="button" aria-label="steps-editor-discard-yes" onClick={onClose} className={`${btn} bg-amber-600 text-white`}>
              {t.processes.discard}
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 pt-1">
          <button type="button" aria-label="steps-editor-cancel" onClick={requestClose} disabled={saving} className={secondary}>
            {t.common.cancel}
          </button>
          <button type="button" aria-label="steps-editor-save" onClick={() => void save()}
            disabled={saving || !dirty || invalidWait} className={`${btn} bg-blue-600 text-white`}>
            {saving ? t.common.saving : t.processes.save_steps}
          </button>
        </div>
      )}
    </section>
  );
}

/** Active Price Book items (REVEAL excluded: the backend rejects them on a
 * surface template). NULL-price items are selectable and labelled. Archived
 * items are not offered: the backend never accepts a NEW archived occurrence. */
function StepItemPicker({ onPick, onCancel }: { onPick: (item: PriceItem) => void; onCancel: () => void }) {
  const { t } = useI18n();
  const [items, setItems] = useState<PriceItem[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [search, setSearch] = useState('');

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    fetchPriceItems({ archived: 'active' })
      .then((resp) => {
        if (cancelled) return;
        setItems(resp.items.filter((item) => item.category !== 'REVEAL' && !item.is_archived));
        setState('ready');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const name = (item: PriceItem): string => {
    if (item.display_name) return item.display_name;
    if (item.name_key) {
      const localized = resolveKey(t, item.name_key);
      if (localized !== item.name_key) return localized;
    }
    return item.code;
  };
  const q = search.trim().toLowerCase();
  const filtered = q
    ? items.filter((item) =>
      name(item).toLowerCase().includes(q)
      || (t.pricebook.categories[item.category] ?? '').toLowerCase().includes(q)
      || item.code.toLowerCase().includes(q))
    : items;

  return (
    <div aria-label="steps-editor-picker" className="rounded-2xl border border-blue-200 bg-white p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">{t.processes.picker_title}</span>
        <button type="button" onClick={onCancel} className="min-h-11 px-3 rounded-xl text-sm text-slate-600">{t.common.cancel}</button>
      </div>
      <input type="search" aria-label="steps-editor-picker-search" value={search} onChange={(e) => setSearch(e.target.value)}
        placeholder={t.work_plan.picker_search} className="w-full min-h-11 px-3 rounded-xl border border-slate-300 text-sm" />
      <p className="text-xs text-slate-500 break-words">{t.processes.picker_hint}</p>
      {state === 'loading' && <p role="status" className="text-sm text-slate-500">{t.processes.picker_loading}</p>}
      {state === 'error' && (
        <div role="alert" className="space-y-2">
          <p className="text-sm text-red-600">{t.processes.picker_error}</p>
          <button type="button" onClick={() => setAttempt((n) => n + 1)} className="min-h-11 px-3 rounded-xl bg-slate-100 text-sm font-semibold">
            {t.work_plan.retry}
          </button>
        </div>
      )}
      {state === 'ready' && filtered.length === 0 && <p className="text-sm text-slate-500">{t.processes.picker_empty}</p>}
      {state === 'ready' && filtered.length > 0 && (
        <ul aria-label="steps-editor-picker-list" className="max-h-80 overflow-y-auto space-y-1.5">
          {filtered.map((item) => (
            <li key={item.id}>
              <button type="button" aria-label={`steps-editor-pick-${item.id}`} onClick={() => onPick(item)}
                className="w-full min-h-11 rounded-xl border border-slate-200 px-3 py-2 text-left text-sm">
                <span className="block font-medium text-slate-900 break-words">{name(item)}</span>
                <span className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-slate-600">
                  <span>{t.pricebook.categories[item.category]}</span>
                  <span>{t.pricebook.units[item.unit]}</span>
                  <span>
                    {item.price === null
                      ? t.processes.no_price
                      : `${formatPrice(item.price)} ${item.currency === 'PLN' ? t.pricebook.currency_symbol : item.currency}`}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
