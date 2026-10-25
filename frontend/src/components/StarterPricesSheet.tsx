import { FormEvent, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchStarterPrices } from '../api/onboarding';
import { updatePriceItem } from '../api/priceItems';
import { useI18n } from '../hooks/useI18n';
import { useMarketEvidence } from '../hooks/useMarketEvidence';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { PriceItem, PriceItemListResponse } from '../types/priceItem';
import { normalizePriceInput } from '../utils/priceFormat';
import { resolveDisplayName } from '../utils/priceItemName';
import { Ico } from './Ico';
import { PriceBookMarket } from './PriceBookMarket';
import { VoiceInput } from './VoiceInput';

interface StarterPricesSheetProps {
  onClose: () => void;
  /** Called after prices were saved (how many), before the sheet closes. */
  onSaved?: (count: number) => void;
  /** A link to the whole price book (the sheet closes first). */
  onOpenAll?: () => void;
  /** Which rows the sheet asks for; the five starter rows by default (the quick estimate asks for the rows of the chosen works). */
  load?: () => Promise<PriceItemListResponse>;
}

/**
 * "5 cen na start" (V2-3): the five price rows a new contractor needs first, in a sheet over the screen. Only the rows that were filled in are saved
 * (through the ordinary price update); the market window of a row is shown as a hint and is never filled in for the owner.
 */
export function StarterPricesSheet({ onClose, onSaved, onOpenAll, load = fetchStarterPrices }: StarterPricesSheetProps) {
  const { t } = useI18n();
  const [items, setItems] = useState<PriceItem[] | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const evidence = useMarketEvidence((items ?? []).map((item) => item.id));
  const text = t.onboarding;

  useTelegramBackButton(true, onClose);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve()
      .then(() => load())
      .then((found) => {
        if (cancelled) return;
        setItems(found.items);
        setValues(Object.fromEntries(found.items.map((item) => [item.id, item.price ?? ''])));
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
    // the rows are read once, when the sheet opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    // the sheet is a portal: React would hand this submit on to a form that holds the component (the quick estimate)
    event.stopPropagation();
    if (!items) return;
    setError(null);
    // only the rows that were changed are sent; an empty field leaves the row as it is
    const changes: { item: PriceItem; value: string }[] = [];
    for (const item of items) {
      const raw = (values[item.id] ?? '').trim();
      if (raw === '' || raw === (item.price ?? '')) continue;
      const state = normalizePriceInput(raw);
      if (!state.ok || state.value === null) {
        setError(text.prices_invalid);
        return;
      }
      changes.push({ item, value: state.value });
    }
    if (changes.length === 0) {
      setError(text.prices_none);
      return;
    }
    setSaving(true);
    try {
      for (const change of changes) await updatePriceItem(change.item.id, { price: change.value });
      onSaved?.(changes.length);
      onClose();
    } catch {
      setError(t.pricebook.error_save);
    } finally {
      setSaving(false);
    }
  };

  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={text.prices_title} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50">
      <form
        aria-label="starter-prices-form"
        onSubmit={handleSubmit}
        className="pe-card w-full max-w-lg rounded-t-2xl sm:rounded-2xl p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-xl space-y-3 max-h-[92vh] overflow-y-auto"
      >
        <h4 className="font-semibold text-slate-900 break-words">{text.prices_title}</h4>
        <p className="text-xs text-slate-600 break-words">{text.prices_intro}</p>
        {!items && !loadFailed && <p className="text-sm text-slate-500 text-center py-4">{t.pricebook.loading}</p>}
        {loadFailed && <p role="alert" className="text-sm text-red-600 break-words">{t.pricebook.error_load}</p>}
        {items?.map((item) => (
          <div key={item.id} aria-label={`starter-price-row-${item.code}`} className="space-y-1">
            <label htmlFor={`starter-price-${item.id}`} className="block text-sm font-semibold text-slate-900 break-words">
              {resolveDisplayName(item, t as unknown as Record<string, unknown>)}
            </label>
            <div className="flex items-center gap-2">
              <VoiceInput name={`starter-price-${item.code}`} className="min-w-0 flex-1" mode="plain" onValue={(value) => setValues((current) => ({ ...current, [item.id]: value.replace('.', ',') }))}>
                <input
                  id={`starter-price-${item.id}`}
                  aria-label={`starter-price-${item.code}`}
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder={t.pricebook.price_not_set}
                  value={values[item.id] ?? ''}
                  onChange={(event) => setValues((current) => ({ ...current, [item.id]: event.target.value }))}
                  className="min-w-0 flex-1 min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm min-w-0 flex-1"
                />
              </VoiceInput>
              <span className="shrink-0 text-sm text-slate-600">PLN / {t.pricebook.units[item.unit]}</span>
            </div>
            <PriceBookMarket itemId={item.id} entry={evidence[item.id]} unitLabel={(value) => t.pricebook.units[value]} />
          </div>
        ))}
        {error && <p role="alert" className="text-sm text-red-600 font-medium break-words">{error}</p>}
        {onOpenAll && (
          <button
            type="button"
            aria-label="starter-prices-all"
            onClick={() => {
              onClose();
              onOpenAll();
            }}
            className="w-full min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-300 text-slate-800 font-medium hover:bg-slate-100"
          >
            <Ico>🏷️</Ico>{text.prices_all}
          </button>
        )}
        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50">
            <Ico>✖️</Ico>{t.common.cancel}
          </button>
          <button
            type="submit"
            disabled={saving || !items}
            className="min-h-11 px-3 py-1 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
          >
            <Ico>💾</Ico>{saving ? t.common.saving : t.common.save}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
