import { useEffect, useMemo, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice } from '../utils/priceFormat';
import { fetchPriceItems } from '../api/priceItems';
import { PriceItem } from '../types/priceItem';

export interface RecommendationPriceItemPickerProps {
  onConfirm: (item: PriceItem) => void;
  onCancel: () => void;
  disabled: boolean;
}

function priceItemTitle(t: ReturnType<typeof useI18n>['t'], item: PriceItem): string {
  if (item.display_name) return item.display_name;
  if (item.name_key) {
    const localized = resolveKey(t, item.name_key);
    if (localized !== item.name_key) return localized;
  }
  return item.code;
}

/** Small standalone PriceItem selector for Stage 11 manual acceptance
 * fallback (11D.2). Deliberately never touches SurfaceWorkPlanEditor's
 * picker/draft/mutation state -- selecting here only reports the chosen
 * PriceItem back to the caller, which submits it through the dedicated
 * recommendation accept endpoint. REVEAL items are excluded because Stage
 * 11 acceptance rejects them (Stage 10's own picker is unaffected).
 */
export function RecommendationPriceItemPicker({
  onConfirm,
  onCancel,
  disabled,
}: RecommendationPriceItemPickerProps) {
  const { t } = useI18n();
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [items, setItems] = useState<PriceItem[]>([]);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadState('loading');
    fetchPriceItems({ archived: 'active' })
      .then((response) => {
        if (cancelled) return;
        setItems(response.items.filter((item) => item.category !== 'REVEAL'));
        setLoadState('ready');
      })
      .catch(() => {
        if (!cancelled) setLoadState('error');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => {
      const name = priceItemTitle(t, item).toLowerCase();
      const cat = t.pricebook.categories[item.category]?.toLowerCase() ?? '';
      return name.includes(q) || cat.includes(q) || item.code.toLowerCase().includes(q);
    });
  }, [items, search, t]);

  const selected = items.find((item) => item.id === selectedId) ?? null;

  return (
    <div
      aria-label={t.recommendations.picker_title}
      className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-white p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <h5 className="text-sm font-semibold text-neutral-900">
          {t.recommendations.picker_title}
        </h5>
        <button
          type="button"
          aria-label={t.recommendations.picker_cancel}
          className="min-h-10 px-3 text-sm font-medium text-neutral-600"
          onClick={onCancel}
          disabled={disabled}
        >
          {t.recommendations.picker_cancel}
        </button>
      </div>

      {loadState === 'loading' ? (
        <p className="text-sm text-neutral-500">{t.recommendations.picker_loading}</p>
      ) : loadState === 'error' ? (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {t.recommendations.picker_error}
        </p>
      ) : (
        <>
          <input
            type="search"
            aria-label={t.recommendations.picker_search}
            placeholder={t.recommendations.picker_search}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="min-h-11 w-full rounded-lg border border-neutral-300 px-3 text-sm"
          />

          {filtered.length === 0 ? (
            <p className="text-sm text-neutral-500">{t.recommendations.picker_empty}</p>
          ) : (
            <ul aria-label={t.recommendations.picker_list} className="max-h-64 flex flex-col gap-1 overflow-y-auto">
              {filtered.map((item) => {
                const isSelected = item.id === selectedId;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      aria-label={`${t.recommendations.picker_item_prefix} ${priceItemTitle(t, item)}`}
                      aria-pressed={isSelected}
                      onClick={() => setSelectedId(item.id)}
                      disabled={disabled}
                      className={`min-h-11 w-full rounded-lg border px-3 py-2 text-left text-sm disabled:opacity-50 ${
                        isSelected
                          ? 'border-blue-600 bg-blue-50'
                          : 'border-neutral-200 bg-white'
                      }`}
                    >
                      <div className="font-medium text-neutral-900 break-words">
                        {priceItemTitle(t, item)}
                      </div>
                      <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-neutral-600">
                        <span>{t.pricebook.categories[item.category]}</span>
                        <span>{t.pricebook.units[item.unit]}</span>
                        <span>
                          {item.price === null
                            ? t.pricebook.price_not_set
                            : `${formatPrice(item.price)} ${
                                item.currency === 'PLN' ? t.pricebook.currency_symbol : item.currency
                              }`}
                        </span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          <button
            type="button"
            aria-label={t.recommendations.picker_confirm}
            className="min-h-11 rounded-lg bg-blue-600 px-3 font-medium text-white disabled:opacity-50"
            disabled={disabled || selected === null}
            onClick={() => {
              if (selected) onConfirm(selected);
            }}
          >
            {t.recommendations.picker_confirm}
          </button>
        </>
      )}
    </div>
  );
}
