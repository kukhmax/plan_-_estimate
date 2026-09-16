import { FormEvent, useEffect, useRef, useState } from 'react';
import {
  fetchSurfaceWorkPlan,
  isSurfaceWorkPlanMissing,
  putSurfaceWorkPlan,
} from '../api/workPlans';
import { useI18n } from '../hooks/useI18n';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import {
  SurfacePlannedWorkRead,
  SurfaceWorkPlanRead,
} from '../types/workPlan';
import { localizeApiError } from '../utils/apiErrors';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice } from '../utils/priceFormat';

interface SurfaceWorkPlanEditorProps {
  projectId: string;
  roomId: string;
  surfaceId: string;
  surfaceName: string;
  onClose: () => void;
}

type LoadState = 'loading' | 'ready' | 'error';

interface WorkPlanBaseline {
  substrate: SubstrateValue | '';
  qualityTarget: QualityLevelValue | null;
}

const SUBSTRATES: readonly SubstrateValue[] = [
  'CONCRETE',
  'GYPSUM_PLASTER',
  'CEMENT_LIME_PLASTER',
  'GYPSUM_BOARD',
  'PAINTED',
  'OTHER',
];
const S_QUALITY_LEVELS: readonly QualityLevelValue[] = ['S1', 'S2', 'S3', 'S4'];
const Q_QUALITY_LEVELS: readonly QualityLevelValue[] = ['Q1', 'Q2', 'Q3', 'Q4'];
const ALL_QUALITY_LEVELS: readonly QualityLevelValue[] = [
  ...S_QUALITY_LEVELS,
  ...Q_QUALITY_LEVELS,
];

function qualityLevelsForSubstrate(substrate: SubstrateValue | ''): readonly QualityLevelValue[] {
  if (substrate === 'GYPSUM_BOARD') return Q_QUALITY_LEVELS;
  if (
    substrate === 'CONCRETE' ||
    substrate === 'GYPSUM_PLASTER' ||
    substrate === 'CEMENT_LIME_PLASTER'
  ) {
    return S_QUALITY_LEVELS;
  }
  if (substrate === 'PAINTED' || substrate === 'OTHER') return ALL_QUALITY_LEVELS;
  return [];
}

export function SurfaceWorkPlanEditor({
  projectId,
  roomId,
  surfaceId,
  surfaceName,
  onClose,
}: SurfaceWorkPlanEditorProps) {
  const { t } = useI18n();
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [hasPlan, setHasPlan] = useState(false);
  const [substrate, setSubstrate] = useState<SubstrateValue | ''>('');
  const [qualityTarget, setQualityTarget] = useState<QualityLevelValue | null>(null);
  const [plannedWorks, setPlannedWorks] = useState<SurfacePlannedWorkRead[]>([]);
  const [baseline, setBaseline] = useState<WorkPlanBaseline>({
    substrate: '',
    qualityTarget: null,
  });
  const loadGeneration = useRef(0);

  const editorId = `work-plan-editor-${surfaceId}`;
  const qualityLevels = qualityLevelsForSubstrate(substrate);
  const dirty = substrate !== baseline.substrate || qualityTarget !== baseline.qualityTarget;

  const describeError = (error: unknown, fallback: string): string => {
    const detail = localizeApiError(error, t);
    return /^Request failed(?: \(\d+\))?$/.test(detail) ? fallback : detail;
  };

  const hydrate = (plan: SurfaceWorkPlanRead | null) => {
    const nextSubstrate = plan?.substrate ?? '';
    const nextQuality = plan?.quality_target ?? null;
    setHasPlan(plan !== null);
    setSubstrate(nextSubstrate);
    setQualityTarget(nextQuality);
    setPlannedWorks(plan?.planned_works ?? []);
    setBaseline({ substrate: nextSubstrate, qualityTarget: nextQuality });
  };

  useEffect(() => {
    const generation = ++loadGeneration.current;
    setLoadState('loading');
    setLoadError(null);
    setSaveError(null);
    setSaved(false);
    setSaving(false);

    void fetchSurfaceWorkPlan(projectId, roomId, surfaceId)
      .then((plan) => {
        if (loadGeneration.current !== generation) return;
        hydrate(plan);
        setLoadState('ready');
      })
      .catch((error: unknown) => {
        if (loadGeneration.current !== generation) return;
        if (isSurfaceWorkPlanMissing(error)) {
          hydrate(null);
          setLoadState('ready');
          return;
        }
        setLoadError(describeError(error, t.work_plan.error_load));
        setLoadState('error');
      });

    return () => {
      if (loadGeneration.current === generation) loadGeneration.current += 1;
    };
  }, [loadAttempt, projectId, roomId, surfaceId, t]);

  const substrateLabel = (value: SubstrateValue): string => {
    const labels: Record<SubstrateValue, string> = {
      CONCRETE: t.inspections.substrate_concrete,
      GYPSUM_PLASTER: t.inspections.substrate_gypsum_plaster,
      CEMENT_LIME_PLASTER: t.inspections.substrate_cement_lime_plaster,
      GYPSUM_BOARD: t.inspections.substrate_gypsum_board,
      PAINTED: t.inspections.substrate_painted,
      OTHER: t.inspections.substrate_other,
    };
    return labels[value];
  };

  const handleSubstrateChange = (next: SubstrateValue | '') => {
    const nextLevels = qualityLevelsForSubstrate(next);
    setSubstrate(next);
    setQualityTarget((current) => {
      if (next === 'PAINTED' || next === 'OTHER') return null;
      return current !== null && nextLevels.includes(current) ? current : null;
    });
    setSaveError(null);
    setSaved(false);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (loadState !== 'ready' || !substrate || !dirty || saving) return;

    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const plan = await putSurfaceWorkPlan(projectId, roomId, surfaceId, {
        substrate,
        quality_target: qualityTarget,
        // PUT is full replacement; occurrence order and duplicates must remain exact.
        price_item_ids: plannedWorks.map((work) => work.price_item_id),
      });
      hydrate(plan);
      setSaved(true);
    } catch (error) {
      setSaveError(describeError(error, t.work_plan.error_save));
    } finally {
      setSaving(false);
    }
  };

  const plannedWorkName = (work: SurfacePlannedWorkRead): string => {
    const item = work.price_item;
    if (!item) return t.work_plan.unavailable_item;
    if (item.display_name) return item.display_name;
    if (item.name_key) {
      const localized = resolveKey(t, item.name_key);
      if (localized !== item.name_key) return localized;
    }
    return t.work_plan.unavailable_item;
  };

  return (
    <section
      id={editorId}
      aria-label={`work-plan-editor-${surfaceId}`}
      className="w-full min-w-0 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] p-3 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h5 className="text-sm font-bold text-[var(--tg-theme-text-color)] break-words">
            {t.work_plan.title}
          </h5>
          <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{surfaceName}</p>
        </div>
        <button
          type="button"
          aria-label={`close-work-plan-${surfaceId}`}
          onClick={onClose}
          disabled={saving}
          className="min-h-11 px-3 rounded-xl border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)] font-semibold disabled:opacity-60"
        >
          {t.common.close}
        </button>
      </div>

      {loadState === 'loading' && (
        <p role="status" className="py-4 text-sm text-center text-[var(--tg-theme-hint-color)]">
          {t.work_plan.loading}
        </p>
      )}

      {loadState === 'error' && (
        <div role="alert" className="space-y-2">
          <p className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)]">
            {t.work_plan.error_load}
          </p>
          {loadError && loadError !== t.work_plan.error_load && (
            <p className="text-xs text-[var(--tg-theme-destructive-text-color)] break-words">{loadError}</p>
          )}
          <button
            type="button"
            aria-label={`retry-work-plan-${surfaceId}`}
            onClick={() => setLoadAttempt((current) => current + 1)}
            className="w-full min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold"
          >
            {t.work_plan.retry}
          </button>
        </div>
      )}

      {loadState === 'ready' && (
        <form aria-label={`work-plan-form-${surfaceId}`} onSubmit={(event) => void handleSubmit(event)} className="space-y-3">
          {!hasPlan && (
            <p className="text-sm text-[var(--tg-theme-hint-color)]">{t.work_plan.no_plan}</p>
          )}

          <label className="block text-sm font-medium text-[var(--tg-theme-text-color)]">
            {t.inspections.substrate}
            <select
              aria-label={`work-plan-substrate-${surfaceId}`}
              value={substrate}
              onChange={(event) => handleSubstrateChange(event.target.value as SubstrateValue | '')}
              disabled={saving}
              className="mt-1 w-full min-h-11 rounded-xl border px-3 py-2 text-base disabled:opacity-60"
            >
              <option value="">{t.inspections.select_substrate}</option>
              {SUBSTRATES.map((value) => (
                <option key={value} value={value}>{substrateLabel(value)}</option>
              ))}
            </select>
          </label>

          <label className="block text-sm font-medium text-[var(--tg-theme-text-color)]">
            {t.inspections.quality_target}
            <select
              aria-label={`work-plan-quality-${surfaceId}`}
              value={qualityTarget ?? ''}
              onChange={(event) => {
                setQualityTarget(event.target.value === '' ? null : event.target.value as QualityLevelValue);
                setSaveError(null);
                setSaved(false);
              }}
              disabled={saving || substrate === ''}
              className="mt-1 w-full min-h-11 rounded-xl border px-3 py-2 text-base disabled:opacity-60"
            >
              <option value="">{t.inspections.quality_optional}</option>
              {qualityLevels.map((level) => (
                <option key={level} value={level}>{t.pricebook.quality[level]}</option>
              ))}
            </select>
          </label>

          <div className="space-y-2 min-w-0">
            <h6 className="text-sm font-semibold text-[var(--tg-theme-text-color)]">
              {t.work_plan.planned_works}
            </h6>
            {plannedWorks.length === 0 ? (
              <p className="text-sm text-[var(--tg-theme-hint-color)]">{t.work_plan.no_works}</p>
            ) : (
              <ol aria-label={`planned-works-${surfaceId}`} className="space-y-2">
                {plannedWorks.map((work) => {
                  const item = work.price_item;
                  return (
                    <li
                      key={work.id}
                      aria-label={`planned-work-${work.id}`}
                      className="min-w-0 rounded-lg border border-[var(--tg-control-border-color)] p-2"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <span className="min-w-0 text-sm font-semibold text-[var(--tg-theme-text-color)] break-words">
                          {plannedWorkName(work)}
                        </span>
                        {item?.is_archived && (
                          <span className="text-xs text-[var(--tg-theme-destructive-text-color)]">
                            {t.pricebook.archived_badge}
                          </span>
                        )}
                      </div>
                      {item ? (
                        <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-[var(--tg-theme-hint-color)]">
                          <span>{t.pricebook.categories[item.category]}</span>
                          <span>{t.pricebook.units[item.unit]}</span>
                          <span>{t.pricebook.scopes[item.price_scope]}</span>
                          {item.quality_level && <span>{t.pricebook.quality[item.quality_level]}</span>}
                          <span>
                            {item.price === null
                              ? t.pricebook.price_not_set
                              : `${formatPrice(item.price)} ${item.currency === 'PLN' ? t.pricebook.currency_symbol : item.currency}`}
                          </span>
                        </div>
                      ) : (
                        <p className="mt-1 text-xs text-[var(--tg-theme-hint-color)]">{t.work_plan.unavailable_item}</p>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
            <p className="text-xs text-[var(--tg-theme-hint-color)]">{t.work_plan.preview_read_only}</p>
          </div>

          {saveError && (
            <div role="alert" className="space-y-1">
              <p className="text-sm font-semibold text-[var(--tg-theme-destructive-text-color)]">
                {t.work_plan.error_save}
              </p>
              {saveError !== t.work_plan.error_save && (
                <p className="text-xs text-[var(--tg-theme-destructive-text-color)] break-words">{saveError}</p>
              )}
            </div>
          )}
          {saved && (
            <p role="status" className="text-sm text-[var(--tg-theme-text-color)]">
              {t.work_plan.saved}
            </p>
          )}

          <button
            type="submit"
            aria-label={`save-work-plan-${surfaceId}`}
            disabled={!substrate || !dirty || saving}
            className="w-full min-h-11 px-3 rounded-xl bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)] font-semibold disabled:opacity-60"
          >
            {saving ? t.common.saving : t.common.save}
          </button>
        </form>
      )}
    </section>
  );
}
