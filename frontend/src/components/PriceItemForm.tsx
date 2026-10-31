import { forwardRef, useEffect, useRef, useState } from 'react';
import { createPriceItem, updatePriceItem } from '../api/priceItems';
import { useI18n } from '../hooks/useI18n';
import { QualityLevelValue } from '../types/checklist';
import {
  PRICE_CATEGORIES,
  PRICE_QUALITY_LEVELS,
  PRICE_SCOPES,
  PRICE_UNITS,
  PriceCategoryValue,
  PriceItem,
  PriceItemCreatePayload,
  PriceScopeValue,
  PriceUnitValue,
} from '../types/priceItem';
import { normalizePriceInput } from '../utils/priceFormat';
import { resolveKey } from '../utils/i18nKeys';
import { Ico } from './Ico';
import { VoiceInput } from './VoiceInput';

/**
 * Shared Price Book create/edit form (Stage 10G.4 extraction).
 *
 * Originally inline in PriceBook.tsx (the Cennik screen); extracted so the
 * exact same contract, validation, and money/name/quality semantics can be
 * reused for inline "+ Dodaj nową pracę do cennika" creation from the Reveal
 * Work and Surface Work Plan pickers, without a second divergent
 * implementation. Cennik's own visual behavior and aria-labels are
 * unchanged — this component renders byte-for-byte the same markup it
 * replaced.
 */

interface PriceFormState {
  display_name: string;
  category: PriceCategoryValue;
  unit: PriceUnitValue;
  price: string;
  price_scope: PriceScopeValue;
  quality_level: QualityLevelValue | '';
}

/** 'unresolved' means an explicit owner choice of NULL ("Do ustalenia") — never
 * an empty/omitted numeric field. Mirrors the Estimate editor's own toggle. */
type PriceEditMode = 'value' | 'unresolved';

function priceModeFor(item: PriceItem | null): PriceEditMode {
  // a catalogue row without a price is opened to type the price (owner 2026-10-31: the one form of every item); an own row without a price
  // was set "do ustalenia" on purpose and opens so
  return item !== null && item.price === null && item.name_key === null ? 'unresolved' : 'value';
}

function formFromItem(item: PriceItem): PriceFormState {
  return {
    display_name: item.display_name ?? '',
    category: item.category,
    unit: item.unit,
    // Seed rows bootstrap with price = null; editing lets the owner enter a price.
    price: item.price ?? '',
    price_scope: item.price_scope,
    quality_level: item.quality_level ?? '',
  };
}

function defaultForm(lockedCategory?: PriceCategoryValue): PriceFormState {
  return {
    display_name: '',
    category: lockedCategory ?? 'PREPARATION',
    unit: 'M2',
    price: '',
    price_scope: 'LABOR',
    quality_level: '',
  };
}

export interface PriceItemFormProps {
  /** Present = edit this existing row; absent/null = create a new one. */
  initialItem?: PriceItem | null;
  /** When set, category is fixed and shown as read-only text — never a selector.
   * Used by context-aware inline creation (e.g. REVEAL from the reveal picker)
   * so the owner cannot accidentally create an incompatible item. */
  lockedCategory?: PriceCategoryValue;
  /** Display text for the locked category value (localized by the caller). */
  lockedCategoryLabel?: string;
  /** Categories this caller must never create (e.g. REVEAL on a Surface plan,
   * where reveal work belongs under an opening). Ignored when locked. */
  excludedCategories?: PriceCategoryValue[];
  /** aria-label / id prefix, so this form can be embedded more than once
   * across the app without colliding with Cennik's own form. */
  idPrefix?: string;
  /** Heading override for create mode (defaults to the Cennik "Dodaj pozycję" copy). */
  titleOverride?: string;
  onCancel: () => void;
  onSaved: (item: PriceItem) => void;
}

export const PriceItemForm = forwardRef<HTMLFormElement, PriceItemFormProps>(
  function PriceItemForm(
    {
      initialItem = null,
      lockedCategory,
      lockedCategoryLabel,
      excludedCategories,
      idPrefix = 'price-item',
      titleOverride,
      onCancel,
      onSaved,
    },
    ref,
  ) {
    const { t } = useI18n();
    const [form, setForm] = useState<PriceFormState>(() =>
      initialItem ? formFromItem(initialItem) : defaultForm(lockedCategory),
    );
    const [priceMode, setPriceMode] = useState<PriceEditMode>(() => priceModeFor(initialItem));
    const [formError, setFormError] = useState<string | null>(null);
    const [formPriceError, setFormPriceError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    // owner 2026-10-31: a catalogue row is edited in this same form -- its name may stay the catalogue's (empty field), its category and
    // unit are the catalogue's and fixed (the processes and the estimate rely on them)
    const catalog = initialItem !== null && initialItem.name_key !== null;
    const catalogName = catalog && initialItem?.name_key ? resolveKey(t, initialItem.name_key) : '';
    const initialKeyRef = useRef<string | null>(initialItem?.id ?? null);

    // Re-seed the draft if the target row's identity changes while this form
    // stays mounted (e.g. tapping Edit on a different row without closing).
    useEffect(() => {
      const key = initialItem?.id ?? null;
      if (key !== initialKeyRef.current) {
        initialKeyRef.current = key;
        setForm(initialItem ? formFromItem(initialItem) : defaultForm(lockedCategory));
        setPriceMode(priceModeFor(initialItem));
        setFormError(null);
        setFormPriceError(null);
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialItem]);

    const categoryLabel = (value: PriceCategoryValue) => t.pricebook.categories[value];
    const unitLabel = (value: PriceUnitValue) => t.pricebook.units[value];
    const scopeLabel = (value: PriceScopeValue) => t.pricebook.scopes[value];
    const qualityLabel = (value: QualityLevelValue) => t.pricebook.quality[value];

    const handleFormChange = (field: keyof PriceFormState, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      if (field === 'price') setFormPriceError(null);
      setFormError(null);
    };

    const handleSubmit = async (e: React.FormEvent) => {
      e.preventDefault();
      let priceValue: string | null;
      if (priceMode === 'unresolved') {
        // Explicit owner choice — never an empty/omitted numeric field collapsed into null.
        priceValue = null;
      } else {
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
        priceValue = priceState.value;
      }
      // An owner row always needs a name; a catalogue row keeps the catalogue's name when the field is empty.
      if (!catalog && form.display_name.trim() === '') {
        setFormError(t.pricebook.validation_name_required);
        return;
      }

      setSaving(true);
      setFormError(null);
      setFormPriceError(null);
      const payload: PriceItemCreatePayload = {
        display_name: form.display_name.trim(),
        category: lockedCategory ?? form.category,
        unit: form.unit,
        price: priceValue,
        price_scope: form.price_scope,
        quality_level: form.quality_level === '' ? null : form.quality_level,
      };
      try {
        const saved = initialItem
          ? await updatePriceItem(initialItem.id, payload)
          : await createPriceItem(payload);
        onSaved(saved);
      } catch {
        setFormError(t.pricebook.error_save);
      } finally {
        setSaving(false);
      }
    };

    const priceState = normalizePriceInput(form.price);
    const invalidPrice =
      priceMode === 'value' && !priceState.ok && priceState.reason !== 'empty';

    return (
      <form
        ref={ref}
        aria-label={`${idPrefix}-form`}
        onSubmit={(e) => void handleSubmit(e)}
        className="pe-card rounded-2xl p-4 mb-4 shadow-sm space-y-3"
      >
        <h3 className="font-semibold text-slate-900">
          {initialItem ? t.pricebook.edit_item : (titleOverride ?? t.pricebook.add_item)}
        </h3>
        <div>
          <label className="block text-xs text-slate-500 mb-1" htmlFor={`${idPrefix}-display-name`}>
            {t.pricebook.display_name}
          </label>
          <input
            id={`${idPrefix}-display-name`}
            aria-label={`${idPrefix}-display-name`}
            maxLength={255}
            placeholder={catalog ? catalogName : t.pricebook.display_name}
            value={form.display_name}
            onChange={(e) => handleFormChange('display_name', e.target.value)}
            className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <p className="text-xs text-slate-400 mt-1">{catalog ? t.pricebook.catalog_name_hint : t.pricebook.name_required_hint}</p>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1" htmlFor={`${idPrefix}-category`}>
            {t.pricebook.category}
          </label>
          {lockedCategory || catalog ? (
            <p
              aria-label={`${idPrefix}-category`}
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700"
            >
              {lockedCategory ? (lockedCategoryLabel ?? categoryLabel(lockedCategory)) : categoryLabel(form.category)}
            </p>
          ) : (
            <select
              id={`${idPrefix}-category`}
              aria-label={`${idPrefix}-category`}
              value={form.category}
              onChange={(e) => handleFormChange('category', e.target.value)}
              className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
            >
              {PRICE_CATEGORIES.filter(
                (value) => value === form.category || !excludedCategories?.includes(value),
              ).map((value) => (
                <option key={value} value={value}>{categoryLabel(value)}</option>
              ))}
            </select>
          )}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-xs text-slate-500 mb-1" htmlFor={`${idPrefix}-unit`}>
              {t.pricebook.unit}
            </label>
            {catalog ? (
              <>
                <p aria-label={`${idPrefix}-unit`} className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700">
                  {unitLabel(form.unit)}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{t.pricebook.unit_fixed_hint}</p>
              </>
            ) : (
              <select
                id={`${idPrefix}-unit`}
                aria-label={`${idPrefix}-unit`}
                value={form.unit}
                onChange={(e) => handleFormChange('unit', e.target.value)}
                className="w-full min-h-11 border border-slate-200 rounded-lg px-2.5 py-2 text-sm"
              >
                {PRICE_UNITS.map((value) => (
                  <option key={value} value={value}>{unitLabel(value)}</option>
                ))}
              </select>
            )}
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1" htmlFor={`${idPrefix}-scope`}>
              {t.pricebook.price_scope}
            </label>
            <select
              id={`${idPrefix}-scope`}
              aria-label={`${idPrefix}-scope`}
              value={form.price_scope}
              onChange={(e) => handleFormChange('price_scope', e.target.value)}
              className="w-full min-h-11 border border-slate-200 rounded-lg px-2.5 py-2 text-sm"
            >
              {PRICE_SCOPES.map((value) => (
                <option key={value} value={value}>{scopeLabel(value)}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1" htmlFor={`${idPrefix}-price`}>
            {t.pricebook.price}
          </label>
          <label className="flex items-center gap-2 min-h-[44px]">
            <input
              type="checkbox"
              aria-label={`${idPrefix}-price-unresolved`}
              checked={priceMode === 'unresolved'}
              onChange={(e) => {
                setPriceMode(e.target.checked ? 'unresolved' : 'value');
                setFormPriceError(null);
              }}
              className="w-5 h-5 shrink-0"
            />
            <span className="text-sm text-slate-700">{t.pricebook.price_unresolved}</span>
          </label>
          {priceMode === 'value' && (
            <VoiceInput name="price" mode="plain" onValue={(value) => handleFormChange('price', value.replace('.', ','))}>
              <input
                id={`${idPrefix}-price`}
                aria-label={`${idPrefix}-price`}
                type="text"
                inputMode="decimal"
                placeholder={t.pricebook.price_placeholder}
                value={form.price}
                onChange={(e) => handleFormChange('price', e.target.value)}
                className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm min-w-0 flex-1"
              />
            </VoiceInput>
          )}
          {formPriceError && (
            <p role="alert" className="text-sm text-red-600 font-medium mt-1">
              {formPriceError}
            </p>
          )}
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1" htmlFor={`${idPrefix}-quality`}>
            {t.pricebook.quality_level}
          </label>
          <select
            id={`${idPrefix}-quality`}
            aria-label={`${idPrefix}-quality`}
            value={form.quality_level}
            onChange={(e) => handleFormChange('quality_level', e.target.value)}
            className="w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            <option value="">{t.pricebook.quality_none}</option>
            <optgroup label={t.pricebook.quality_group_s}>
              {PRICE_QUALITY_LEVELS.filter((value) => value.startsWith('S')).map((value) => (
                <option key={value} value={value}>{qualityLabel(value)}</option>
              ))}
            </optgroup>
            <optgroup label={t.pricebook.quality_group_q}>
              {PRICE_QUALITY_LEVELS.filter((value) => value.startsWith('Q')).map((value) => (
                <option key={value} value={value}>{qualityLabel(value)}</option>
              ))}
            </optgroup>
          </select>
          <p className="text-xs text-slate-400 mt-1">{t.pricebook.quality_helper}</p>
        </div>
        <p className="text-xs text-slate-400">{t.pricebook.currency_note}</p>
        {formError && (
          <p role="alert" className="text-sm text-red-600 font-medium">{formError}</p>
        )}
        <div className="flex gap-2 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="min-h-11 px-3 py-2 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
          >
            <Ico>✖️</Ico>{t.common.cancel}
          </button>
          <button
            type="submit"
            disabled={saving || invalidPrice}
            className="min-h-11 px-3 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
          >
            <Ico>💾</Ico>{saving ? t.common.saving : t.common.save}
          </button>
        </div>
      </form>
    );
  },
);
