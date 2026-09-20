import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import {
  archivePriceItem,
  fetchPriceItems,
  restorePriceItem,
  updatePriceItem,
} from '../api/priceItems';
import { useI18n } from '../hooks/useI18n';
import { useMarketEvidence } from '../hooks/useMarketEvidence';
import { QualityLevelValue } from '../types/checklist';
import {
  PRICE_CATEGORIES,
  PriceItem,
  PriceCategoryValue,
  PriceScopeValue,
  PriceUnitValue,
} from '../types/priceItem';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice, normalizePriceInput } from '../utils/priceFormat';
import { PriceBookMarket } from './PriceBookMarket';
import { PriceItemForm } from './PriceItemForm';

type Tab = 'active' | 'archived';

/** display_name > localized name_key > em-dash. Never the machine code. */
function resolveDisplayName(item: PriceItem, t: Record<string, unknown>): string {
  if (item.display_name) return item.display_name;
  if (item.name_key) {
    const resolved = resolveKey(t, item.name_key);
    if (resolved !== item.name_key) return resolved;
  }
  return '—';
}

/** Seeded catalog rows carry a name_key; owner-created rows never do. */
function isCatalogItem(item: PriceItem): boolean {
  return item.name_key !== null;
}

interface PriceBookProps {
  resetSignal?: number;
}

export function PriceBook({ resetSignal }: PriceBookProps) {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>('active');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<PriceCategoryValue | ''>('');
  const [items, setItems] = useState<PriceItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<PriceItem | null>(null);

  // Inline owner-price editor for catalog rows (Stage 9E.8). Catalog rows carry
  // canonical metadata (name, unit, category, quality), so only the commercial
  // price is editable — and it is edited in place instead of via the global form.
  const [inlineId, setInlineId] = useState<string | null>(null);
  const [inlinePrice, setInlinePrice] = useState('');
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [inlineSaving, setInlineSaving] = useState(false);

  const formRef = useRef<HTMLFormElement | null>(null);

  // The full Add/Edit form (custom rows) renders above the Price Book list.
  // With a multi-row catalog the form lands far above the tapped card, so
  // without this scroll opening Add or Edit appears to do nothing on a phone.
  // Catalog rows edit inline and never scroll (Stage 9E.8).
  useLayoutEffect(() => {
    if (showForm) {
      formRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    }
  }, [showForm]);

  // Per-item market evidence (read-only; cached, never re-fetched per render).
  const evidence = useMarketEvidence(items.map((item) => item.id));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPriceItems({
        archived: tab,
        search: search.trim() || undefined,
        category: category || undefined,
      });
      setItems(data.items);
      setTotal(data.total);
    } catch {
      setError(t.pricebook.error_load);
    } finally {
      setLoading(false);
    }
  }, [tab, search, category, t.pricebook.error_load]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (resetSignal) {
      setShowForm(false);
      setInlineId(null);
      setInlineError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetSignal]);

  const categoryLabel = (value: PriceCategoryValue) => t.pricebook.categories[value];
  const unitLabel = (value: PriceUnitValue) => t.pricebook.units[value];
  const scopeLabel = (value: PriceScopeValue) => t.pricebook.scopes[value];
  const qualityLabel = (value: QualityLevelValue) => t.pricebook.quality[value];

  const closeInline = () => {
    setInlineId(null);
    setInlineError(null);
  };

  const openInlineEdit = (item: PriceItem) => {
    setShowForm(false);
    setInlineId(item.id);
    setInlinePrice(item.price ?? '');
    setInlineError(null);
  };

  const handleInlinePriceChange = (value: string) => {
    setInlinePrice(value);
    setInlineError(null);
  };

  const handleInlineSubmit = async (item: PriceItem) => {
    const priceState = normalizePriceInput(inlinePrice);
    if (!priceState.ok) {
      setInlineError(
        priceState.reason === 'empty'
          ? t.pricebook.validation_price_required
          : priceState.reason === 'precision'
            ? t.pricebook.validation_price_precision
            : priceState.reason === 'negative'
              ? t.pricebook.validation_price_negative
              : t.pricebook.validation_price_format,
      );
      return;
    }
    setInlineSaving(true);
    setInlineError(null);
    try {
      const updated = await updatePriceItem(item.id, { price: priceState.value ?? '' });
      setItems((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
      closeInline();
    } catch {
      setInlineError(t.pricebook.error_save);
    } finally {
      setInlineSaving(false);
    }
  };

  const openCreate = () => {
    closeInline();
    setEditing(null);
    setShowForm(true);
  };

  const openEdit = (item: PriceItem) => {
    closeInline();
    setEditing(item);
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditing(null);
  };

  const handleFormSaved = () => {
    closeForm();
    void load();
  };

  const handleArchive = async (item: PriceItem) => {
    closeInline();
    try {
      await archivePriceItem(item.id);
      setActionError(null);
      setNotice(t.pricebook.archived_notice);
      void load();
    } catch {
      setNotice(null);
      setActionError(t.pricebook.error_archive);
    }
  };

  const handleRestore = async (item: PriceItem) => {
    try {
      await restorePriceItem(item.id);
      setActionError(null);
      setNotice(t.pricebook.restored_notice);
      void load();
    } catch {
      setNotice(null);
      setActionError(t.pricebook.error_restore);
    }
  };

  const inlineState = normalizePriceInput(inlinePrice);
  const invalidInlinePrice = !inlineState.ok && inlineState.reason !== 'empty';
  const emptyMessage = search.trim()
    ? t.pricebook.empty_search
    : tab === 'archived'
      ? t.pricebook.empty_archived
      : t.pricebook.empty;

  return (
    <section aria-label="price-book-section" className="w-full mt-4">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-bold text-slate-900">{t.pricebook.title}</h2>
        {total > 0 && (
          <span className="text-xs text-slate-400">{total}</span>
        )}
      </div>

      <div
        role="tablist"
        aria-label="pricebook-tabs"
        className="flex gap-2 mb-3"
      >
        {(['active', 'archived'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            aria-label={`pricebook-tab-${value}`}
            onClick={() => setTab(value)}
            className={`min-h-11 px-4 text-sm font-semibold rounded-xl transition ${
              tab === value ? '' : 'border border-slate-200'
            }`}
            style={
              tab === value
                ? {
                    backgroundColor: 'var(--tg-theme-button-color)',
                    color: 'var(--tg-theme-button-text-color)',
                  }
                : {
                    backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                    color: 'var(--tg-theme-hint-color)',
                  }
            }
          >
            {value === 'active' ? t.pricebook.active_tab : t.pricebook.archived_tab}
          </button>
        ))}
      </div>

      <div className="flex gap-2 mb-3 flex-wrap">
        <input
          aria-label="pricebook-search"
          type="text"
          placeholder={t.pricebook.search_placeholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-0 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          aria-label="pricebook-category-filter"
          value={category}
          onChange={(e) => setCategory(e.target.value as PriceCategoryValue | '')}
          className="border border-slate-200 rounded-xl px-2 py-2 text-sm bg-white"
        >
          <option value="">{t.pricebook.all_categories}</option>
          {PRICE_CATEGORIES.map((value) => (
            <option key={value} value={value}>{categoryLabel(value)}</option>
          ))}
        </select>
      </div>

      <button
        type="button"
        aria-label="add-price-item"
        onClick={openCreate}
        className="min-h-11 w-full px-3 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
      >
        + {t.pricebook.add_item}
      </button>

      {showForm && (
        <PriceItemForm
          ref={formRef}
          initialItem={editing}
          onCancel={closeForm}
          onSaved={handleFormSaved}
        />
      )}

      {notice && <p role="status" className="text-sm text-emerald-700 mb-3">{notice}</p>}
      {actionError && <p role="alert" className="text-sm text-red-600 mb-3">{actionError}</p>}

      {loading && (
        <p aria-label="pricebook-loading" className="text-sm text-slate-500 text-center py-4">
          {t.pricebook.loading}
        </p>
      )}
      {!loading && error && (
        <p role="alert" className="text-sm text-red-600 text-center py-4">{error}</p>
      )}
      {!loading && !error && items.length === 0 && (
        <p aria-label="pricebook-empty" className="text-sm text-slate-400 text-center py-6">
          {emptyMessage}
        </p>
      )}
      {!loading && !error && items.length > 0 && (
        <ul aria-label="pricebook-list" className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              aria-label={`price-item-${item.id}`}
              className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-slate-900 text-sm break-words">
                  {resolveDisplayName(item, t)}
                </h4>
                {item.is_archived && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                    {t.pricebook.archived_badge}
                  </span>
                )}
              </div>
              {item.quality_level && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-800 font-medium mt-0.5 inline-block">
                  {qualityLabel(item.quality_level)}
                </span>
              )}
              <p className="text-xs text-slate-500 mt-0.5">
                {categoryLabel(item.category)}
                {item.price_scope !== 'LABOR' && (
                  <> · {scopeLabel(item.price_scope)}</>
                )}
              </p>

              {inlineId === item.id ? (
                <div aria-label={`inline-price-edit-${item.id}`} className="mt-2 space-y-2">
                  <p className="text-[10px] uppercase tracking-wide text-slate-400 font-medium">
                    {t.pricebook.market.my_price}
                  </p>
                  <div>
                    <label
                      className="block text-xs text-slate-500 mb-1"
                      htmlFor={`inline-price-input-${item.id}`}
                    >
                      {t.pricebook.price}
                    </label>
                    <input
                      id={`inline-price-input-${item.id}`}
                      aria-label={`inline-price-input-${item.id}`}
                      type="text"
                      inputMode="decimal"
                      placeholder={t.pricebook.price_placeholder}
                      value={inlinePrice}
                      onChange={(e) => handleInlinePriceChange(e.target.value)}
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    />
                    {inlineError && (
                      <p role="alert" className="text-sm text-red-600 font-medium mt-1">
                        {inlineError}
                      </p>
                    )}
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-1">{t.pricebook.unit}</p>
                    <p className="text-sm font-semibold text-slate-900">{unitLabel(item.unit)}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{t.pricebook.unit_fixed_hint}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      aria-label={`inline-price-cancel-${item.id}`}
                      onClick={closeInline}
                      className="min-h-11 flex-1 px-3 py-2 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
                    >
                      {t.common.cancel}
                    </button>
                    <button
                      type="button"
                      aria-label={`inline-price-save-${item.id}`}
                      onClick={() => void handleInlineSubmit(item)}
                      disabled={inlineSaving || invalidInlinePrice}
                      className="min-h-11 flex-1 px-3 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
                    >
                      {inlineSaving ? t.common.saving : t.common.save}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="text-[10px] uppercase tracking-wide text-slate-400 font-medium mt-1">
                    {t.pricebook.market.my_price}
                  </p>
                  <p className="text-base font-extrabold text-slate-900 mt-1">
                    {item.price === null ? (
                      <span className="text-slate-500">
                        {t.pricebook.price_not_set}
                      </span>
                    ) : (
                      <span className="text-emerald-700">
                        {formatPrice(item.price)} {t.pricebook.currency_symbol}
                      </span>
                    )}
                    <span className="text-slate-500 text-sm"> / {unitLabel(item.unit)}</span>
                  </p>
                </>
              )}

              {item.is_archived ? (
                <button
                  type="button"
                  aria-label={`restore-price-item-${item.id}`}
                  onClick={() => void handleRestore(item)}
                  className="mt-2 min-h-11 w-full px-3 py-2 text-xs rounded-lg bg-emerald-50 text-emerald-700 font-medium hover:bg-emerald-100 transition"
                >
                  {t.common.restore}
                </button>
              ) : (
                inlineId !== item.id && (
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      aria-label={`edit-price-item-${item.id}`}
                      onClick={() =>
                        isCatalogItem(item) ? openInlineEdit(item) : openEdit(item)
                      }
                      className="min-h-11 flex-1 px-3 py-2 text-xs rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                    >
                      {t.common.edit}
                    </button>
                    <button
                      type="button"
                      aria-label={`archive-price-item-${item.id}`}
                      onClick={() => void handleArchive(item)}
                      className="min-h-11 flex-1 px-3 py-2 text-xs rounded-lg bg-orange-50 text-orange-700 font-medium hover:bg-orange-100 transition"
                    >
                      {t.common.archive}
                    </button>
                  </div>
                )
              )}

              <PriceBookMarket itemId={item.id} entry={evidence[item.id]} unitLabel={unitLabel} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}