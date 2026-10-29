import { useEffect, useState } from 'react';
import { fetchCompatibleTemplates } from '../api/workflowTemplates';
import { useI18n } from '../hooks/useI18n';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { WorkflowTemplateRead, WorkflowTemplateStepRead } from '../types/workflowTemplate';
import { resolveKey } from '../utils/i18nKeys';
import { Ico } from './Ico';

interface RoomPlanProcessPickerProps {
  target: 'walls' | 'ceiling';
  substrate: SubstrateValue;
  quality: QualityLevelValue | '';
  /** The list already has works: the steps may replace them or go after them. */
  hasWorks: boolean;
  nameOf: (priceItemId: string) => string;
  onPick: (priceItemIds: string[], mode: 'replace' | 'append') => void;
  onClose: () => void;
}

type ListState = 'loading' | 'ready' | 'error';

/**
 * B1: the processes of the price book ("Procesy") inside the plan of a room. The processes that fit the substrate, the class and the kind of
 * surface are offered; a chosen one puts its steps into the list of the sheet (required ones always, optional ones by a tick, off at first).
 * Nothing is saved here: the sheet saves the list as before.
 */
export function RoomPlanProcessPicker({ target, substrate, quality, hasWorks, nameOf, onPick, onClose }: RoomPlanProcessPickerProps) {
  const { t } = useI18n();
  const text = t.roomplan;
  const [state, setState] = useState<ListState>('loading');
  const [templates, setTemplates] = useState<WorkflowTemplateRead[]>([]);
  const [chosen, setChosen] = useState<WorkflowTemplateRead | null>(null);
  const [optionalOn, setOptionalOn] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (quality === '') return undefined;
    let cancelled = false;
    setState('loading');
    setChosen(null);
    void fetchCompatibleTemplates({ substrate, quality_target: quality, surface_type: target === 'walls' ? 'WALL' : 'CEILING' })
      .then((resp) => {
        if (cancelled) return;
        setTemplates(resp.items.filter((tpl) => tpl.steps.length > 0));
        setState('ready');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [substrate, quality, target]);

  const templateName = (tpl: WorkflowTemplateRead): string => {
    if (tpl.display_name) return tpl.display_name;
    if (tpl.name_key) {
      const localized = resolveKey(t, tpl.name_key);
      if (localized !== tpl.name_key) return localized;
    }
    return tpl.code;
  };
  const archived = (step: WorkflowTemplateStepRead) => !step.price_item || step.price_item.is_archived;
  const steps = [...(chosen?.steps ?? [])].sort((a, b) => a.position - b.position);
  const blocked = steps.some((step) => !step.is_optional && archived(step));
  const picked = steps.filter((step) => !archived(step) && (!step.is_optional || optionalOn.has(step.id)));

  const pick = (mode: 'replace' | 'append') => onPick(picked.map((step) => step.price_item_id), mode);
  const toggle = (id: string) =>
    setOptionalOn((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const button = 'w-full min-h-11 px-3 text-sm font-semibold rounded-xl break-words disabled:opacity-40';

  return (
    <div aria-label={`room-plan-${target}-process`} className="rounded-xl border border-blue-200 bg-blue-50/60 p-3 space-y-2">
      {quality === '' ? (
        <p className="text-xs text-slate-600 break-words">{text.process_need_quality}</p>
      ) : state === 'loading' ? (
        <p className="text-xs text-slate-500">{t.work_plan.tpl_loading}</p>
      ) : state === 'error' ? (
        <p role="alert" className="text-xs text-red-600 break-words">{t.work_plan.tpl_load_error}</p>
      ) : templates.length === 0 ? (
        <p className="text-xs text-slate-600 break-words">{t.work_plan.tpl_empty}</p>
      ) : chosen === null ? (
        <ul className="space-y-1.5">
          {templates.map((tpl) => (
            <li key={tpl.id}>
              <button
                type="button"
                aria-label={`room-plan-process-${tpl.id}`}
                onClick={() => {
                  setChosen(tpl);
                  setOptionalOn(new Set()); // optional steps start off, as in the plan of a wall
                }}
                className="w-full min-h-11 px-3 py-2 text-left rounded-xl border border-slate-200 pe-surface hover:bg-slate-50"
              >
                <span className="block text-sm font-semibold text-slate-900 break-words">{templateName(tpl)}</span>
                <span className="block text-xs text-slate-500">{text.process_steps.replace('{n}', String(tpl.steps.length))}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <>
          <p className="text-sm font-semibold text-slate-900 break-words">{templateName(chosen)}</p>
          <ul className="space-y-1">
            {steps.map((step, index) => {
              const gone = archived(step);
              const on = !gone && (!step.is_optional || optionalOn.has(step.id));
              return (
                <li key={step.id}>
                  <label className="flex items-start gap-2 min-h-11 py-1.5">
                    <input
                      type="checkbox"
                      aria-label={`room-plan-process-step-${index}`}
                      checked={on}
                      disabled={gone || !step.is_optional}
                      onChange={() => toggle(step.id)}
                      className="mt-0.5 h-5 w-5 shrink-0"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm text-slate-900 break-words">{index + 1}. {nameOf(step.price_item_id)}</span>
                      <span className={`block text-xs break-words ${gone ? 'text-amber-700' : 'text-slate-500'}`}>
                        {gone ? t.work_plan.tpl_archived_item : step.is_optional ? t.work_plan.tpl_optional : t.work_plan.tpl_required}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
          {blocked && <p role="alert" className="text-xs text-amber-700 break-words">{t.work_plan.tpl_required_archived}</p>}
          {hasWorks ? (
            <div className="grid grid-cols-1 gap-1.5">
              <button type="button" aria-label={`room-plan-${target}-process-replace`} disabled={blocked || picked.length === 0} onClick={() => pick('replace')} className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>
                {text.process_replace}
              </button>
              <button type="button" aria-label={`room-plan-${target}-process-append`} disabled={blocked || picked.length === 0} onClick={() => pick('append')} className={`${button} border border-slate-300 text-slate-800 pe-surface hover:bg-slate-100`}>
                {text.process_append}
              </button>
            </div>
          ) : (
            <button type="button" aria-label={`room-plan-${target}-process-insert`} disabled={blocked || picked.length === 0} onClick={() => pick('replace')} className={`${button} bg-blue-600 text-white hover:bg-blue-700`}>
              {text.process_insert.replace('{n}', String(picked.length))}
            </button>
          )}
          <button type="button" aria-label={`room-plan-${target}-process-back`} onClick={() => setChosen(null)} className={`${button} border border-slate-200 text-slate-700 pe-surface hover:bg-slate-50 font-normal`}>
            {text.process_back}
          </button>
        </>
      )}
      <button type="button" aria-label={`room-plan-${target}-process-close`} onClick={onClose} className="w-full min-h-11 px-3 text-sm rounded-xl text-slate-600 hover:bg-slate-100">
        <Ico>✖️</Ico>{t.common.close}
      </button>
    </div>
  );
}
