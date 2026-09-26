import { ReactNode, useEffect, useState } from 'react';
import { fetchWorkflowTemplates } from '../api/workflowTemplates';
import { useI18n } from '../hooks/useI18n';
import { SubstrateValue } from '../types/checklist';
import { SurfaceTypeValue } from '../types/surface';
import { SurfacePriceItemSummaryRead } from '../types/workPlan';
import { WorkflowTemplateRead } from '../types/workflowTemplate';
import { resolveKey } from '../utils/i18nKeys';
import { templateDescription, templateStepNote } from '../utils/workflowTemplateText';

/**
 * Stage 13F.3 — Cennik → Procesy: read-only management of technological
 * workflow templates (list + detail). Presentation only: every value comes
 * from the canonical template API (steps, live PriceItem summaries, derived
 * `is_default`). Editing, archive/restore and duplication are later 13F
 * sub-stages; applying a template stays in the Stage 13E work-plan flow.
 */

type ArchiveTab = 'active' | 'archived';
type LoadState = 'loading' | 'ready' | 'error';

const SURFACE_FILTERS: SurfaceTypeValue[] = ['WALL', 'CEILING', 'FLOOR', 'OTHER'];

export function WorkflowTemplateManager() {
  const { t } = useI18n();
  const [tab, setTab] = useState<ArchiveTab>('active');
  const [surfaceType, setSurfaceType] = useState<SurfaceTypeValue | null>(null);
  const [templates, setTemplates] = useState<WorkflowTemplateRead[]>([]);
  const [state, setState] = useState<LoadState>('loading');
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<WorkflowTemplateRead | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    fetchWorkflowTemplates({ archived: tab, surface_type: surfaceType ?? undefined })
      .then((resp) => {
        if (cancelled) return;
        setTemplates(resp.items);
        setState('ready');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [tab, surfaceType, attempt]);

  const templateName = (tpl: WorkflowTemplateRead): string => {
    if (tpl.display_name) return tpl.display_name;
    if (tpl.name_key) {
      const localized = resolveKey(t, tpl.name_key);
      if (localized !== tpl.name_key) return localized;
    }
    return tpl.code;
  };

  const itemName = (item: SurfacePriceItemSummaryRead | null): string => {
    if (!item) return t.work_plan.unavailable_item;
    if (item.display_name) return item.display_name;
    if (item.name_key) {
      const localized = resolveKey(t, item.name_key);
      if (localized !== item.name_key) return localized;
    }
    return item.code;
  };

  const surfaceLabel: Record<SurfaceTypeValue, string> = {
    WALL: t.surfaces.wall,
    CEILING: t.surfaces.ceiling,
    FLOOR: t.surfaces.floor,
    OTHER: t.surfaces.other,
  };
  const substrateLabel = (value: SubstrateValue): string => {
    const key = `substrate_${value.toLowerCase()}` as keyof typeof t.inspections;
    return String(t.inspections[key] ?? value);
  };
  const joinOrAny = (values: string[]): string => (values.length ? values.join(', ') : t.processes.any);

  const archivedSteps = (tpl: WorkflowTemplateRead) =>
    tpl.steps.filter((s) => !s.price_item || s.price_item.is_archived).length;
  const noPriceSteps = (tpl: WorkflowTemplateRead) =>
    tpl.steps.filter((s) => s.price_item && !s.price_item.is_archived && s.price_item.price === null).length;

  const chip = (active: boolean) =>
    `min-h-11 px-3 text-sm font-semibold rounded-xl transition ${
      active ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
    }`;

  // ---- read-only detail -----------------------------------------------------
  if (selected) {
    const tpl = selected;
    const description = templateDescription(t, tpl);
    return (
      <section aria-label={`process-detail-${tpl.id}`} className="space-y-3">
        <button
          type="button"
          aria-label="process-detail-back"
          onClick={() => setSelected(null)}
          className="w-full min-h-11 px-3 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 text-left"
        >
          ← {t.processes.back}
        </button>
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
          <div className="space-y-1.5">
            <h3 className="text-base font-bold text-slate-900 break-words">{templateName(tpl)}</h3>
            <div className="flex flex-wrap gap-1.5">
              {tpl.is_default && <Badge tone="blue">{t.processes.default_badge}</Badge>}
              {tpl.is_archived && <Badge tone="orange">{t.processes.archived_badge}</Badge>}
            </div>
            <p className="text-xs text-slate-500 break-all">
              {t.processes.code_label}: <span className="font-mono">{tpl.code}</span>
            </p>
          </div>
          {description && (
            <p aria-label="process-description" className="text-xs text-slate-600 whitespace-pre-line break-words">
              {description}
            </p>
          )}
          <dl aria-label="process-applicability" className="space-y-1 text-xs">
            <Row label={t.processes.surfaces_label} value={joinOrAny(tpl.applies_to_surface_types.map((s) => surfaceLabel[s]))} />
            <Row label={t.processes.substrates_label} value={joinOrAny(tpl.applies_to_substrates.map(substrateLabel))} />
            <Row label={t.processes.quality_label} value={joinOrAny(tpl.applies_to_quality)} />
          </dl>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-2">
          <h4 className="text-sm font-semibold text-slate-900">
            {t.processes.steps_title} ({tpl.steps.length})
          </h4>
          {tpl.steps.length === 0 ? (
            <p aria-label="process-steps-empty" className="text-sm text-slate-500 break-words">
              {t.processes.empty_steps}
            </p>
          ) : (
            <ol aria-label="process-steps" className="space-y-2">
              {tpl.steps.map((step, index) => {
                const item = step.price_item;
                const archived = !item || item.is_archived;
                const note = templateStepNote(t, step);
                return (
                  <li
                    key={step.id}
                    aria-label={`process-step-${step.id}`}
                    className="rounded-xl border border-slate-200 p-3 space-y-1"
                  >
                    <div className="flex items-start gap-2">
                      <span className="shrink-0 text-sm font-semibold text-slate-400">{index + 1}.</span>
                      <span className="flex-1 min-w-0 text-sm font-medium text-slate-900 break-words">{itemName(item)}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 text-xs pl-6">
                      <Badge tone={step.is_optional ? 'slate' : 'blue'}>
                        {step.is_optional ? t.work_plan.tpl_optional : t.work_plan.tpl_required}
                      </Badge>
                      {item && <span className="text-slate-500">{t.pricebook.units[item.unit]}</span>}
                      {step.wait_after_hours !== null && (
                        <span className="text-slate-500 break-words">
                          {t.work_plan.tpl_wait.replace('{hours}', String(step.wait_after_hours))}
                        </span>
                      )}
                      {archived && <Badge tone="red">{t.work_plan.tpl_archived_item}</Badge>}
                      {!archived && item && item.price === null && <Badge tone="amber">{t.processes.no_price}</Badge>}
                    </div>
                    {note && (
                      <p aria-label={`process-step-note-${step.id}`} className="text-xs text-slate-500 break-words pl-6">{note}</p>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </section>
    );
  }

  // ---- list -----------------------------------------------------------------
  return (
    <section aria-label="processes-section" className="space-y-3">
      <div role="tablist" aria-label="processes-archive-tabs" className="flex flex-wrap gap-2">
        {(['active', 'archived'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            aria-label={`processes-tab-${value}`}
            onClick={() => setTab(value)}
            className={chip(tab === value)}
          >
            {value === 'active' ? t.processes.tab_active : t.processes.tab_archived}
          </button>
        ))}
      </div>

      <div aria-label="processes-surface-filter" className="space-y-1">
        <span className="block text-xs font-medium text-slate-500">{t.processes.surfaces_label}</span>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            aria-pressed={surfaceType === null}
            aria-label="processes-filter-all"
            onClick={() => setSurfaceType(null)}
            className={chip(surfaceType === null)}
          >
            {t.processes.filter_all}
          </button>
          {SURFACE_FILTERS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={surfaceType === value}
              aria-label={`processes-filter-${value}`}
              onClick={() => setSurfaceType(value)}
              className={chip(surfaceType === value)}
            >
              {surfaceLabel[value]}
            </button>
          ))}
        </div>
      </div>

      {state === 'loading' && <p role="status" className="text-sm text-slate-500">{t.work_plan.tpl_loading}</p>}
      {state === 'error' && (
        <div role="alert" className="space-y-2">
          <p className="text-sm text-red-600">{t.work_plan.tpl_load_error}</p>
          <button type="button" className={chip(false)} onClick={() => setAttempt((n) => n + 1)}>
            {t.work_plan.retry}
          </button>
        </div>
      )}
      {state === 'ready' && templates.length === 0 && (
        <p aria-label="processes-empty" className="text-sm text-slate-500 text-center py-6 break-words">
          {tab === 'archived' ? t.processes.empty_archived : t.processes.empty}
        </p>
      )}
      {state === 'ready' && templates.length > 0 && (
        <ul aria-label="processes-list" className="space-y-2">
          {templates.map((tpl) => {
            const optional = tpl.steps.filter((s) => s.is_optional).length;
            const archived = archivedSteps(tpl);
            const noPrice = noPriceSteps(tpl);
            return (
              <li key={tpl.id}>
                <button
                  type="button"
                  aria-label={`process-card-${tpl.id}`}
                  onClick={() => setSelected(tpl)}
                  className="w-full min-h-11 text-left bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-1.5"
                >
                  <span className="block text-sm font-semibold text-slate-900 break-words">{templateName(tpl)}</span>
                  <span className="flex flex-wrap gap-1.5">
                    {tpl.is_default && <Badge tone="blue">{t.processes.default_badge}</Badge>}
                    {tpl.is_archived && <Badge tone="orange">{t.processes.archived_badge}</Badge>}
                  </span>
                  <span className="block text-xs text-slate-500 break-words">
                    {joinOrAny(tpl.applies_to_surface_types.map((s) => surfaceLabel[s]))}
                  </span>
                  <span className="block text-xs text-slate-500 break-words">
                    {t.work_plan.tpl_steps_count.replace('{count}', String(tpl.steps.length))}
                    {optional > 0 && ` · ${t.work_plan.tpl_optional_count.replace('{count}', String(optional))}`}
                  </span>
                  {(archived > 0 || noPrice > 0) && (
                    <span className="block text-xs text-amber-800 break-words">
                      ⚠ {[
                        archived > 0 ? t.processes.warn_archived.replace('{count}', String(archived)) : null,
                        noPrice > 0 ? t.processes.warn_no_price.replace('{count}', String(noPrice)) : null,
                      ].filter(Boolean).join(' · ')}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Badge({ tone, children }: { tone: 'blue' | 'orange' | 'slate' | 'red' | 'amber'; children: ReactNode }) {
  const tones = {
    blue: 'bg-blue-50 text-blue-700',
    orange: 'bg-orange-100 text-orange-700',
    slate: 'bg-slate-100 text-slate-700',
    red: 'bg-red-50 text-red-700',
    amber: 'bg-amber-100 text-amber-900',
  };
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium break-words ${tones[tone]}`}>{children}</span>;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-slate-500">{label}</dt>
      <dd className="min-w-0 text-right font-medium text-slate-800 break-words">{value}</dd>
    </div>
  );
}
