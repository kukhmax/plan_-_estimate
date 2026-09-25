import React, { useEffect, useMemo, useState } from 'react';
import { fetchCoefficientGroups } from '../api/coefficients';
import { useI18n } from '../hooks/useI18n';
import { CoefficientGroupRead, CoefficientOptionRead } from '../types/coefficient';
import { PlannedWorkCoefficientOptionRead } from '../types/workPlan';
import {
  calculateEffectivePrice,
  formatPercentageDisplay,
  isPercentageAbove,
  sumPercentages,
} from '../utils/coefficientCalculations';
import {
  coefficientGroupDescription,
  coefficientGroupName,
  coefficientOptionDescription,
  coefficientOptionName,
} from '../utils/coefficientLabels';

// Stage 12G: above this additive total the modal shows a non-blocking hint.
const HIGH_TOTAL_WARNING_THRESHOLD = '50';

interface DescriptionSheetContent {
  title: string;
  text: string;
}

export interface CoefficientAssignmentModalProps {
  isOpen: boolean;
  occurrenceName: string;
  basePrice: string | null;
  currency: string;
  initialOptionIds: string[];
  onApply: (selectedOptions: PlannedWorkCoefficientOptionRead[]) => void;
  onCancel: () => void;
}

export const CoefficientAssignmentModal: React.FC<CoefficientAssignmentModalProps> = ({
  isOpen,
  occurrenceName,
  basePrice,
  currency,
  initialOptionIds,
  onApply,
  onCancel,
}) => {
  const { t } = useI18n();
  const [groups, setGroups] = useState<CoefficientGroupRead[]>([]);
  const [loading, setLoading] = useState(isOpen);
  const [error, setError] = useState<string | null>(null);

  // Map of groupId -> selectedOptionId | null (null = "Brak")
  const [selectedByGroup, setSelectedByGroup] = useState<Record<string, string | null>>({});
  // Read-only description overlay; never touches the selection above.
  const [descriptionSheet, setDescriptionSheet] = useState<DescriptionSheetContent | null>(null);
  // Accordion: at most one group expanded; purely presentational state.
  const [expandedGroupId, setExpandedGroupId] = useState<string | null>(null);

  // Keyed by content, not array identity: parents rebuild `initialOptionIds`
  // on every render, which must not refetch and reset the local selection.
  const initialOptionIdsKey = initialOptionIds.join(',');

  useEffect(() => {
    if (!isOpen) return;
    setExpandedGroupId(null);
    const initialIds = initialOptionIdsKey ? initialOptionIdsKey.split(',') : [];

    let isMounted = true;
    setLoading(true);
    setError(null);

    fetchCoefficientGroups({ archived: 'active' })
      .then((res) => {
        if (!isMounted) return;
        setGroups(res.items);

        // Initialize selections from initialOptionIds
        const initialMap: Record<string, string | null> = {};
        for (const group of res.items) {
          const matchingOption = group.options.find(
            (opt) => !opt.is_archived && initialIds.includes(opt.id),
          );
          initialMap[group.id] = matchingOption ? matchingOption.id : null;
        }
        setSelectedByGroup(initialMap);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : t.coefficients.error_load);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, initialOptionIdsKey, t.coefficients.error_load]);

  // Selected option objects
  const selectedOptions = useMemo(() => {
    const list: Array<{ option: CoefficientOptionRead; group: CoefficientGroupRead }> = [];
    for (const group of groups) {
      const optionId = selectedByGroup[group.id];
      if (optionId) {
        const option = group.options.find((o) => o.id === optionId);
        if (option) {
          list.push({ option, group });
        }
      }
    }
    return list;
  }, [groups, selectedByGroup]);

  // Additive total percentage
  const totalPercentage = useMemo(() => {
    return sumPercentages(selectedOptions.map((s) => s.option.percentage));
  }, [selectedOptions]);

  // Effective price preview
  const effectivePrice = useMemo(() => {
    return calculateEffectivePrice(basePrice, totalPercentage);
  }, [basePrice, totalPercentage]);

  const showHighTotalWarning = isPercentageAbove(totalPercentage, HIGH_TOTAL_WARNING_THRESHOLD);

  if (!isOpen) return null;

  const renderInfoButton = (title: string, text: string | null, testId: string) =>
    text ? (
      <button
        type="button"
        aria-label={t.coefficients.show_description.replace('{name}', title)}
        data-testid={testId}
        onClick={(e) => {
          e.stopPropagation();
          setDescriptionSheet({ title, text });
        }}
        className="shrink-0 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-blue-700 hover:bg-blue-50 active:bg-blue-100"
      >
        <span
          aria-hidden="true"
          className="flex h-6 w-6 items-center justify-center rounded-full border border-blue-300 text-xs font-bold italic"
        >
          i
        </span>
      </button>
    ) : null;

  const handleSelectOption = (groupId: string, optionId: string | null) => {
    setSelectedByGroup((prev) => ({
      ...prev,
      [groupId]: optionId,
    }));
  };

  const handleApply = () => {
    const mapped: PlannedWorkCoefficientOptionRead[] = selectedOptions.map(
      ({ option, group }) => ({
        id: option.id,
        group_id: group.id,
        group_code: group.code,
        code: option.code,
        display_name: option.display_name,
        percentage: option.percentage,
        is_base: option.is_base,
      }),
    );
    onApply(mapped);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="coefficient-modal-title"
    >
      <div
        aria-hidden={descriptionSheet ? true : undefined}
        className="w-full max-w-lg bg-[var(--tg-theme-bg-color,#ffffff)] rounded-t-2xl sm:rounded-2xl shadow-xl flex flex-col max-h-[90vh] overflow-hidden"
      >
        {/* Header */}
        <div className="p-4 border-b border-slate-200 flex items-start justify-between">
          <div className="flex-1 min-w-0 pr-2">
            <h2
              id="coefficient-modal-title"
              className="text-lg font-semibold text-[var(--tg-theme-text-color,#0f172a)] truncate"
            >
              {t.coefficients.modal_title}
            </h2>
            <p className="text-xs text-[var(--tg-theme-hint-color,#64748b)] truncate mt-0.5">
              {occurrenceName}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="shrink-0 min-h-[44px] min-w-[44px] flex items-center justify-center text-slate-400 hover:text-slate-600 rounded-lg"
            aria-label={t.common.close}
          >
            ✕
          </button>
        </div>

        {/* Live Summary Bar */}
        <div className="bg-slate-50 border-b border-slate-200 p-3 grid grid-cols-3 gap-2 text-center">
          <div>
            <div className="text-[10px] uppercase font-semibold text-slate-500">
              {t.coefficients.base_price}
            </div>
            <div className="text-sm font-semibold text-slate-800 truncate mt-0.5">
              {basePrice !== null ? `${basePrice} ${currency}` : t.coefficients.unresolved_price}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-semibold text-slate-500">
              {t.coefficients.adjustment}
            </div>
            <div className="text-sm font-semibold text-blue-600 mt-0.5">
              {formatPercentageDisplay(totalPercentage)}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-semibold text-slate-500">
              {t.coefficients.effective_price}
            </div>
            <div className="text-sm font-semibold text-emerald-600 truncate mt-0.5">
              {effectivePrice !== null
                ? `${effectivePrice} ${currency}`
                : t.coefficients.unresolved_price}
            </div>
          </div>
        </div>

        {/* Content body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading && (
            <div className="py-8 text-center text-sm text-[var(--tg-theme-hint-color,#64748b)]">
              {t.coefficients.loading}
            </div>
          )}

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {error}
            </div>
          )}

          {!loading && !error && groups.length === 0 && (
            <div className="py-8 text-center text-sm text-[var(--tg-theme-hint-color,#64748b)]">
              {t.coefficients.no_groups}
            </div>
          )}

          {!loading &&
            !error &&
            groups.map((group) => {
              const activeOptions = group.options.filter((o) => !o.is_archived);
              const currentSelectedId = selectedByGroup[group.id] ?? null;

              const groupName = coefficientGroupName(group, t);
              const selectedOption =
                currentSelectedId === null
                  ? null
                  : activeOptions.find((o) => o.id === currentSelectedId) ?? null;
              const isExpanded = expandedGroupId === group.id;
              const panelId = `coefficient-group-panel-${group.id}`;

              return (
                <div key={group.id} className="rounded-lg border border-slate-200">
                  <div className="flex items-stretch">
                    <button
                      type="button"
                      data-testid={`coefficient-group-toggle-${group.id}`}
                      aria-expanded={isExpanded}
                      aria-controls={panelId}
                      onClick={() => setExpandedGroupId(isExpanded ? null : group.id)}
                      className="flex min-h-[44px] min-w-0 flex-1 items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-slate-50 active:bg-slate-100"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-slate-800 break-words">
                          {groupName}
                        </span>
                        <span
                          data-testid={`coefficient-group-summary-${group.id}`}
                          className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-slate-500 break-words"
                        >
                          {selectedOption ? (
                            <>
                              <span className="text-blue-800">
                                {coefficientOptionName(group.code, selectedOption, t)}
                              </span>
                              {selectedOption.is_base && (
                                <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                                  {t.coefficients.base_badge}
                                </span>
                              )}
                            </>
                          ) : (
                            <span>{t.coefficients.none_option}</span>
                          )}
                        </span>
                      </span>
                      <span
                        data-testid={`coefficient-group-percent-${group.id}`}
                        className={`shrink-0 font-mono text-xs ${
                          selectedOption ? 'font-bold text-blue-700' : 'text-slate-400'
                        }`}
                      >
                        {selectedOption ? formatPercentageDisplay(selectedOption.percentage) : '—'}
                      </span>
                      <span
                        aria-hidden="true"
                        className={`shrink-0 text-lg leading-none text-slate-400 transition-transform ${
                          isExpanded ? 'rotate-90' : ''
                        }`}
                      >
                        ›
                      </span>
                    </button>
                    {renderInfoButton(
                      groupName,
                      coefficientGroupDescription(group, t),
                      `coefficient-group-info-${group.id}`,
                    )}
                  </div>
                  {isExpanded && (
                  <div id={panelId} className="space-y-1.5 border-t border-slate-100 p-2">
                    {/* "Brak" option */}
                    <label
                      className={`flex min-h-[44px] items-center justify-between p-2.5 rounded-lg border text-sm cursor-pointer transition-colors ${
                        currentSelectedId === null
                          ? 'border-blue-500 bg-blue-50/50 text-blue-900 font-medium'
                          : 'border-slate-200 hover:bg-slate-50 text-slate-700'
                      }`}
                    >
                      <div className="flex items-center space-x-2.5 min-w-0">
                        <input
                          type="radio"
                          name={`group-${group.id}`}
                          checked={currentSelectedId === null}
                          onChange={() => handleSelectOption(group.id, null)}
                          className="h-4 w-4 text-blue-600 focus:ring-blue-500"
                        />
                        <span className="truncate">{t.coefficients.none_option}</span>
                      </div>
                    </label>

                    {/* Active options */}
                    {activeOptions.map((option) => {
                      const isSelected = currentSelectedId === option.id;
                      const optionName = coefficientOptionName(group.code, option, t);
                      return (
                        <div
                          key={option.id}
                          className={`flex min-h-[44px] items-center rounded-lg border text-sm transition-colors ${
                            isSelected
                              ? 'border-blue-500 bg-blue-50/50 text-blue-900 font-medium'
                              : 'border-slate-200 hover:bg-slate-50 text-slate-700'
                          }`}
                        >
                        <label className="flex min-h-[44px] min-w-0 flex-1 items-center justify-between p-2.5 cursor-pointer">
                          <div className="flex items-center space-x-2.5 min-w-0">
                            <input
                              type="radio"
                              name={`group-${group.id}`}
                              checked={isSelected}
                              onChange={() => handleSelectOption(group.id, option.id)}
                              className="h-4 w-4 text-blue-600 focus:ring-blue-500"
                            />
                            <span className="truncate">{optionName}</span>
                            {option.is_base && (
                              <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                                {t.coefficients.base_badge}
                              </span>
                            )}
                          </div>
                          <span
                            className={`shrink-0 ml-2 font-mono text-xs ${
                              isSelected ? 'text-blue-700 font-bold' : 'text-slate-600'
                            }`}
                          >
                            {formatPercentageDisplay(option.percentage)}
                          </span>
                        </label>
                        {renderInfoButton(
                          optionName,
                          coefficientOptionDescription(group.code, option, t),
                          `coefficient-option-info-${option.id}`,
                        )}
                        </div>
                      );
                    })}
                  </div>
                  )}
                </div>
              );
            })}
        </div>

        {showHighTotalWarning && (
          <div
            role="status"
            aria-label="coefficient-high-total-warning"
            className="mx-4 mb-2 mt-1 rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-900 whitespace-pre-line break-words"
          >
            {t.coefficients.high_total_warning.replace(
              '{percent}',
              formatPercentageDisplay(totalPercentage),
            )}
          </div>
        )}

        {/* Footer actions */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center gap-3">
          <button
            type="button"
            onClick={onCancel}
            aria-label="coefficient-modal-cancel"
            className="flex-1 min-h-[44px] px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 active:bg-slate-100"
          >
            {t.coefficients.cancel}
          </button>
          <button
            type="button"
            onClick={handleApply}
            // Applying before the catalog loads would replace the occurrence's
            // existing selection with an empty one.
            disabled={loading || error !== null}
            aria-label="coefficient-modal-apply"
            className="flex-1 min-h-[44px] px-4 py-2 text-sm font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50"
          >
            {t.coefficients.apply}
          </button>
        </div>
      </div>

      {descriptionSheet && (
        <div
          className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="coefficient-description-title"
          data-testid="coefficient-description-sheet"
          onClick={(e) => {
            if (e.target === e.currentTarget) setDescriptionSheet(null);
          }}
        >
          <div className="w-full max-w-lg max-h-[80vh] flex flex-col overflow-hidden rounded-t-2xl sm:rounded-2xl bg-[var(--tg-theme-bg-color,#ffffff)] shadow-xl">
            <div className="flex items-start justify-between gap-2 border-b border-slate-200 p-4">
              <h3
                id="coefficient-description-title"
                className="min-w-0 text-base font-semibold text-[var(--tg-theme-text-color,#0f172a)] break-words"
              >
                {descriptionSheet.title}
              </h3>
              <button
                type="button"
                onClick={() => setDescriptionSheet(null)}
                aria-label={t.coefficients.close}
                className="shrink-0 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-slate-500 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 text-sm text-[var(--tg-theme-text-color,#0f172a)] whitespace-pre-line break-words">
              {descriptionSheet.text}
            </div>
            <div className="border-t border-slate-200 p-4">
              <button
                type="button"
                onClick={() => setDescriptionSheet(null)}
                className="w-full min-h-[44px] rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                {t.coefficients.close}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
