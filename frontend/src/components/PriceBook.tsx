import React, { useCallback, useEffect, useState } from 'react';
import {
  archivePriceItem,
  createPriceItem,
  fetchPriceItems,
  restorePriceItem,
  updatePriceItem,
} from '../api/priceItems';
import { useI18n } from '../hooks/useI18n';
import { useMarketEvidence } from '../hooks/useMarketEvidence';
import { QualityLevelValue } from '../types/checklist';
import {
  PRICE_CATEGORIES,
  PRICE_QUALITY_LEVELS,
  PRICE_SCOPES,
  PRICE_UNITS,
  PriceItem,
  PriceItemCreatePayload,
  PriceCategoryValue,
  PriceScopeValue,
  PriceUnitValue,
} from '../types/priceItem';
import { resolveKey } from '../utils/i18nKeys';
import { formatPrice, normalizePriceInput } from '../utils/priceFormat';
import { PriceBookMarket } from './PriceBookMarket';

type Tab = 'active' | 'archived';

interface PriceFormState {
  display_name: string;
  category: PriceCategoryValue;
  unit: PriceUnitValue;
  price: string;
  price_scope: PriceScopeValue;
  quality_level: QualityLevelValue | '';
}

const DEFAULT_FORM: PriceFormState = {
  display_name: '',
  category: 'PREPARATION',
  unit: 'M2',
  price: '',
  price_scope: 'LABOR',
  quality_level: '',
};

/** display_name > localized name_key > em-dash. Never the machine code. */
function resolveDisplayName(item: PriceItem, t: Record<string, unknown>): string {
  if (item.display_name) return item.display_name;
  if (item.name_key) {
    const resolved = resolveKey(t, item.name_key);
    if (resolved !== item.name_key) return resolved;
  }
  return '—';
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
  const [form, setForm] = useState<PriceFormState>(DEFAULT_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [formPriceError, setFormPriceError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [openOptionsId, setOpenOptionsId] = useState<string | null>(null);

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
      setFormError(null);
      setFormPriceError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetSignal]);

  const categoryLabel = (value: PriceCategoryValue) => t.pricebook.categories[value];
  const unitLabel = (value: PriceUnitValue) => t.pricebook.units[value];
  const scopeLabel = (value: PriceScopeValue) => t.pricebook.scopes[value];
  const qualityLabel = (value: QualityLevelValue) => t.pricebook.quality[value];

  const formFromItem = (item: PriceItem): PriceFormState => ({
    display_name: item.display_name ?? '',
    category: item.category,
    unit: item.unit,
    price: item.price,
    price_scope: item.price_scope,
    quality_level: item.quality_level ?? '',
  });

  const openCreate = () => {
    setEditing(null);
    setForm(DEFAULT_FORM);
    setFormError(null);
    setFormPriceError(null);
    setShowForm(true);
  };

  const openEdit = (item: PriceItem) => {
    setEditing(item);
    setForm(formFromItem(item));
    setFormError(null);
    setFormPriceError(null);
    setShowForm(true);
    setOpenOptionsId(null);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditing(null);
    setFormError(null);
    setFormPriceError(null);
  };

  const handleFormChange = (field: keyof PriceFormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (field === 'price') setFormPriceError(null);
    setFormError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const priceState = normalizePriceInput(form.price);
    if (!priceState.ok) {
      setFormPriceError(
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
    if (editing === null || editing.name_key === null) {
      // Custom rows (and every created row is custom) require a display name;
      // a blank name on a seeded row instead clears the display override.
      if (form.display_name.trim() === '') {
        setFormError(t.pricebook.validation_name_required);
        return;
      }
    }

    setSaving(true);
    setFormError(null);
    setFormPriceError(null);
    const payload: PriceItemCreatePayload = {
      display_name: form.display_name.trim(),
      category: form.category,
      unit: form.unit,
      price: priceState.value ?? '',
      price_scope: form.price_scope,
      quality_level: form.quality_level === '' ? null : form.quality_level,
    };
    try {
      if (editing) {
        await updatePriceItem(editing.id, payload);
      } else {
        await createPriceItem(payload);
      }
      closeForm();
      void load();
    } catch {
      setFormError(t.pricebook.error_save);
    } finally {
      setSaving(false);
    }
  };

  const handleArchive = async (item: PriceItem) => {
    setOpenOptionsId(null);
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

  const priceState = normalizePriceInput(form.price);
  const invalidPrice =
    !priceState.ok && priceState.reason !== 'empty';
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
        <form
          aria-label="price-item-form"
          onSubmit={handleSubmit}
          className="bg-white border border-slate-200 rounded-2xl p-4 mb-4 shadow-sm space-y-3"
        >
          <h3 className="font-semibold text-slate-900">
            {editing ? t.pricebook.edit_item : t.pricebook.add_item}
          </h3>
          <div>
            <label className="block text-xs text-slate-500 mb-1" htmlFor="price-item-display-name">
              {t.pricebook.display_name}
            </label>
            <input
              id="price-item-display-name"
              aria-label="price-item-display-name"
              maxLength={255}
              placeholder={t.pricebook.display_name}
              value={form.display_name}
              onChange={(e) => handleFormChange('display_name', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
            {editing === null && (
              <p className="text-xs text-slate-400 mt-1">{t.pricebook.name_required_hint}</p>
            )}
            {editing?.name_key && form.display_name.trim() === '' && (
              <p className="text-xs text-slate-500 mt-1">
                {t.pricebook.seed_identity}: {resolveKey(t, editing.name_key)}
              </p>
            )}
          </div>
          <select
            aria-label="price-item-category"
            value={form.category}
            onChange={(e) => handleFormChange('category', e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            {PRICE_CATEGORIES.map((value) => (
              <option key={value} value={value}>{categoryLabel(value)}</option>
            ))}
          </select>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-slate-500 mb-1" htmlFor="price-item-unit">
                {t.pricebook.unit}
              </label>
              <select
                id="price-item-unit"
                aria-label="price-item-unit"
                value={form.unit}
                onChange={(e) => handleFormChange('unit', e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm"
              >
                {PRICE_UNITS.map((value) => (
                  <option key={value} value={value}>{unitLabel(value)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1" htmlFor="price-item-scope">
                {t.pricebook.price_scope}
              </label>
              <select
                id="price-item-scope"
                aria-label="price-item-scope"
                value={form.price_scope}
                onChange={(e) => handleFormChange('price_scope', e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm"
              >
                {PRICE_SCOPES.map((value) => (
                  <option key={value} value={value}>{scopeLabel(value)}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1" htmlFor="price-item-price">
              {t.pricebook.price}
            </label>
            <input
              id="price-item-price"
              aria-label="price-item-price"
              type="text"
              inputMode="decimal"
              placeholder={t.pricebook.price_placeholder}
              value={form.price}
              onChange={(e) => handleFormChange('price', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
            {formPriceError && (
              <p role="alert" className="text-sm text-red-600 font-medium mt-1">
                {formPriceError}
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1" htmlFor="price-item-quality">
              {t.pricebook.quality_level}
            </label>
            <select
              id="price-item-quality"
              aria-label="price-item-quality"
              value={form.quality_level}
              onChange={(e) => handleFormChange('quality_level', e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">{t.pricebook.quality_none}</option>
              {PRICE_QUALITY_LEVELS.map((value) => (
                <option key={value} value={value}>{qualityLabel(value)}</option>
              ))}
            </select>
          </div>
          <p className="text-xs text-slate-400">{t.pricebook.currency_note}</p>
          {formError && (
            <p role="alert" className="text-sm text-red-600 font-medium">{formError}</p>
          )}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={closeForm}
              className="min-h-11 px-3 py-2 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
            >
              {t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={saving || invalidPrice}
              className="min-h-11 px-3 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              {saving ? t.common.saving : t.common.save}
            </button>
          </div>
        </form>
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
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-semibold text-slate-900 text-sm">
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
                  <p className="text-[10px] uppercase tracking-wide text-slate-400 font-medium">
                    {t.pricebook.market.my_price}
                  </p>
                  <p className="text-base font-extrabold text-slate-900 mt-1">
                    <span className="text-emerald-700">
                      {formatPrice(item.price)} {t.pricebook.currency_symbol}
                    </span>
                    <span className="text-slate-500 text-sm"> / {unitLabel(item.unit)}</span>
                  </p>
                </div>
                <div className="flex-shrink-0">
                  {item.is_archived ? (
                    <button
                      type="button"
                      aria-label={`restore-price-item-${item.id}`}
                      onClick={() => void handleRestore(item)}
                      className="min-h-11 px-3 py-2 text-xs rounded-lg bg-emerald-50 text-emerald-700 font-medium hover:bg-emerald-100 transition"
                    >
                      {t.common.restore}
                    </button>
                  ) : (
                    <button
                      type="button"
                      aria-label={`price-item-options-${item.id}`}
                      onClick={() =>
                        setOpenOptionsId(openOptionsId === item.id ? null : item.id)
                      }
                      className="min-h-11 px-3 py-2 text-xs rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                    >
                      {t.pricebook.options}
                    </button>
                  )}
                </div>
              </div>
              {!item.is_archived && openOptionsId === item.id && (
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    aria-label={`edit-price-item-${item.id}`}
                    onClick={() => openEdit(item)}
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
              )}
              <PriceBookMarket itemId={item.id} entry={evidence[item.id]} unitLabel={unitLabel} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}