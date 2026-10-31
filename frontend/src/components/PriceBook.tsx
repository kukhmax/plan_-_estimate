import {
  lazy,
  Suspense,
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
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { useTrades } from '../hooks/useTrades';
import { QualityLevelValue } from '../types/checklist';
import {
  PRICE_CATEGORIES,
  PriceItem,
  PriceCategoryValue,
  PriceScopeValue,
  PriceUnitValue,
} from '../types/priceItem';
import { priceItemMatches, priceItemRank, resolveDisplayName } from '../utils/priceItemName';
import plDictionary from '../locales/pl.json';
import { StarterPricesSheet } from './StarterPricesSheet';
import { formatPrice } from '../utils/priceFormat';
import { HubTile } from './HubTile';
import { PriceBookMarket } from './PriceBookMarket';
import { PriceItemForm } from './PriceItemForm';
import { Ico } from './Ico';
import { packNameHint } from '../utils/nameHints';

// Secondary screen, only shown on the "Współczynniki" tab — kept out of the
// main bundle.
const CoefficientCatalogManager = lazy(() =>
  import('./CoefficientCatalogManager').then((m) => ({ default: m.CoefficientCatalogManager })),
);
// Stage 13F.3: Cennik → Procesy (technological workflow templates, read-only).
const WorkflowTemplateManager = lazy(() =>
  import('./WorkflowTemplateManager').then((m) => ({ default: m.WorkflowTemplateManager })),
);

type Tab = 'active' | 'archived';
type MainTab = 'items' | 'coefficients' | 'processes';

interface PriceBookProps {
  resetSignal?: number;
  /** An overlay above the screen (the main menu, the account dialog) owns the Telegram BackButton while it is open. */
  backSuspended?: boolean;
}

export function PriceBook({ resetSignal, backSuspended = false }: PriceBookProps) {
  const { t } = useI18n();
  // The price opens as a hub of three tiles (Stage 16K.6), like an object; null = the hub.
  const [mainTab, setMainTab] = useState<MainTab | null>(null);
  const [tab, setTab] = useState<Tab>('active');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<PriceCategoryValue | ''>('');
  const [items, setItems] = useState<PriceItem[]>([]);
  const [total, setTotal] = useState(0);
  // V2-13: the categories of the trades the owner does not work in are hidden; "show all" lifts it for the moment (it is not saved).
  const trades = useTrades();
  const [showAllTrades, setShowAllTrades] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<PriceItem | null>(null);

  // owner 2026-10-31: the list is one line per item ("name — price ✏️"); a tap opens its details (the market, archiving), ✏️ opens the
  // one form of every item (catalogue or own) right under its line
  const [openId, setOpenId] = useState<string | null>(null);

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

  // Per-item market evidence (read-only; cached, never re-fetched per render) -- read for a row when its details are first opened
  // (owner 2026-10-31: the list is one line per item; it no longer asks the market of every item at once)
  const [opened, setOpened] = useState<string[]>([]);
  const evidence = useMarketEvidence(opened);
  const query = search.trim();
  const found = query
    ? items
        .filter((item) => priceItemMatches(item, query, [t as unknown as Record<string, unknown>, plDictionary as unknown as Record<string, unknown>], [t.pricebook.categories[item.category]]))
        .map((item, index) => ({ item, index, rank: priceItemRank(item, query, t as unknown as Record<string, unknown>) }))
        .sort((a, b) => a.rank - b.rank || a.index - b.index)
        .map((entry) => entry.item)
    : items;
  const shownItems = showAllTrades ? found : found.filter((item) => trades.categoryVisible(item.category));
  const hiddenByTrades = found.length - shownItems.length;
  const shownCategories = showAllTrades ? PRICE_CATEGORIES : PRICE_CATEGORIES.filter((value) => trades.categoryVisible(value));
  useEffect(() => {
    if (!showAllTrades && category && !trades.categoryVisible(category)) setCategory('');
  }, [showAllTrades, category, trades]);

  const [starterOpen, setStarterOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // the search is done here, over the names the owner sees (UX walk A1: the catalogue rows have only a key, the server cannot match their names)
      const data = await fetchPriceItems({
        archived: tab,
        category: category || undefined,
      });
      setItems(data.items);
      setTotal(data.total);
    } catch {
      setError(t.pricebook.error_load);
    } finally {
      setLoading(false);
    }
  }, [tab, category, t.pricebook.error_load]);

  useEffect(() => {
    if (mainTab === 'items') void load();
  }, [load, mainTab]);

  useTelegramBackButton(mainTab !== null && !backSuspended, () => setMainTab(null));

  useEffect(() => {
    if (resetSignal) {
      setMainTab(null);
      setShowForm(false);
      setEditing(null);
      setOpenId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetSignal]);

  const categoryLabel = (value: PriceCategoryValue) => t.pricebook.categories[value];
  const unitLabel = (value: PriceUnitValue) => t.pricebook.units[value];
  const scopeLabel = (value: PriceScopeValue) => t.pricebook.scopes[value];
  const qualityLabel = (value: QualityLevelValue) => t.pricebook.quality[value];

  // UX walk B7: the market reference becomes the owner's price by one tap of his, only for a row that has no price yet
  const [referenceBusy, setReferenceBusy] = useState<string | null>(null);
  const takeReference = async (item: PriceItem, price: string) => {
    if (referenceBusy) return;
    setReferenceBusy(item.id);
    try {
      const updated = await updatePriceItem(item.id, { price });
      setItems((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
    } catch {
      setError(t.pricebook.error_save);
    } finally {
      setReferenceBusy(null);
    }
  };

  const openCreate = () => {
    setEditing(null);
    setShowForm(true);
  };

  const openEdit = (item: PriceItem) => {
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

  const emptyMessage = search.trim()
    ? t.pricebook.empty_search
    : tab === 'archived'
      ? t.pricebook.empty_archived
      : hiddenByTrades > 0
        ? t.trades.price_all_hidden
        : t.pricebook.empty;

  return (
    <section aria-label="price-book-section" className="w-full mt-4">
      {mainTab === null ? (
        <>
          <nav aria-label="pricebook-hub" className="grid grid-cols-1 gap-3">
            <HubTile icon="🏷️" ariaLabel="pricebook-maintab-items" label={t.coefficients.tab_items} onOpen={() => setMainTab('items')} />
            <HubTile icon="🎚️" ariaLabel="pricebook-maintab-coefficients" label={t.coefficients.tab_coefficients} onOpen={() => setMainTab('coefficients')} />
            <HubTile icon="⚙️" ariaLabel="pricebook-maintab-processes" label={t.processes.tab} onOpen={() => setMainTab('processes')} />
          </nav>
        </>
      ) : (
        <nav aria-label="pricebook-navigation" className="flex items-center gap-1.5 flex-wrap text-xs text-[var(--tg-theme-hint-color)] mb-2">
          <button
            type="button"
            aria-label="back-to-pricebook"
            onClick={() => setMainTab(null)}
            className="inline-flex items-center min-h-11 pr-1 font-semibold text-blue-700 hover:underline"
          >
            {t.pricebook.title}
          </button>
          <span>/</span>
          <span className="font-medium text-[var(--tg-theme-text-color)]">
            {mainTab === 'items' ? t.coefficients.tab_items : mainTab === 'coefficients' ? t.coefficients.tab_coefficients : t.processes.tab}
          </span>
          {mainTab === 'items' && (query ? shownItems.length : total - hiddenByTrades) > 0 && <span className="ml-auto text-xs text-slate-400">{query ? shownItems.length : total - hiddenByTrades}</span>}
        </nav>
      )}

      {mainTab === null ? null : mainTab === 'processes' ? (
        <Suspense
          fallback={<div className="py-8 text-center text-sm text-slate-500">{t.work_plan.tpl_loading}</div>}
        >
          <WorkflowTemplateManager />
        </Suspense>
      ) : mainTab === 'coefficients' ? (
        <Suspense
          fallback={
            <div className="py-8 text-center text-sm text-slate-500">{t.coefficients.loading}</div>
          }
        >
          <CoefficientCatalogManager />
        </Suspense>
      ) : (
        <>

      {/* V2-3: while no row has a price, the five that matter first are one tap away */}
      {tab === 'active' && !loading && !error && !search.trim() && !category && shownItems.length > 0 && shownItems.every((item) => item.price === null) && (
        <div aria-label="starter-prices-hint" className="pe-card rounded-2xl p-3 mb-3 shadow-sm space-y-2">
          <p className="text-sm font-semibold text-slate-900 break-words">{t.onboarding.prices_hint_title}</p>
          <p className="text-xs text-slate-600 break-words">{t.onboarding.prices_hint_text}</p>
          <button
            type="button"
            aria-label="starter-prices-open"
            onClick={() => setStarterOpen(true)}
            className="w-full min-h-11 px-3 py-1 text-sm font-semibold rounded-xl bg-blue-600 text-white hover:bg-blue-700 transition"
          >
            <Ico>🏷️</Ico>{t.onboarding.prices_open}
          </button>
        </div>
      )}
      {starterOpen && <StarterPricesSheet onClose={() => setStarterOpen(false)} onSaved={() => void load()} />}

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
          className="flex-1 min-w-0 min-h-11 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          aria-label="pricebook-category-filter"
          value={category}
          onChange={(e) => setCategory(e.target.value as PriceCategoryValue | '')}
          className="min-h-11 border border-slate-200 rounded-xl px-2 py-2 text-sm pe-surface"
        >
          <option value="">{t.pricebook.all_categories}</option>
          {shownCategories.map((value) => (
            <option key={value} value={value}>{categoryLabel(value)}</option>
          ))}
        </select>
      </div>

      {trades.anyHidden && (
        <button
          type="button"
          aria-label="pricebook-show-all-trades"
          aria-pressed={showAllTrades}
          onClick={() => setShowAllTrades((value) => !value)}
          className="w-full min-h-11 mb-3 px-3 py-2 text-sm font-medium rounded-xl border border-slate-200 pe-surface text-slate-700 break-words hover:bg-slate-50"
        >
          <Ico>{showAllTrades ? '🙈' : '👁️'}</Ico>
          {showAllTrades ? t.trades.price_hide : `${t.trades.price_show_all}${hiddenByTrades > 0 ? ` (${hiddenByTrades})` : ''}`}
        </button>
      )}

      <button
        type="button"
        aria-label="add-price-item"
        onClick={openCreate}
        className="min-h-11 w-full px-3 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
      >
        <Ico>➕</Ico>{t.pricebook.add_item}
      </button>

      {showForm && editing === null && (
        <PriceItemForm
          ref={formRef}
          initialItem={null}
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
      {!loading && !error && shownItems.length === 0 && (
        <p aria-label="pricebook-empty" className="text-sm text-slate-400 text-center py-6">
          {emptyMessage}
        </p>
      )}
      {!loading && !error && shownItems.length > 0 && (
        <ul aria-label="pricebook-list" className="space-y-1.5">
          {shownItems.map((item) => {
            const open = openId === item.id;
            const hint = packNameHint(t, item.display_name);
            return (
              <li key={item.id} aria-label={`price-item-${item.id}`} className="pe-card rounded-xl shadow-sm">
                <div className="flex items-center gap-1.5 pl-3 pr-1.5 py-1">
                  <button
                    type="button"
                    aria-label={`price-item-toggle-${item.id}`}
                    aria-expanded={open}
                    onClick={() => {
                      setOpenId(open ? null : item.id);
                      if (!open && !opened.includes(item.id)) setOpened((current) => [...current, item.id]);
                    }}
                    className="min-w-0 flex-1 min-h-11 flex items-center gap-2 text-left"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold text-slate-900 text-sm break-words">{resolveDisplayName(item, t)}</span>
                      {/* UX walk: the Polish name of a typical item with its meaning in the language of the screen */}
                      {hint && <span className="block text-xs font-normal text-slate-500 break-words">{hint}</span>}
                      {item.is_archived && (
                        <span className="mt-0.5 inline-block text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                          {t.pricebook.archived_badge}
                        </span>
                      )}
                    </span>
                    <span aria-label={`price-item-price-${item.id}`} className="shrink-0 text-right text-sm font-bold whitespace-nowrap">
                      {item.price === null ? (
                        <span className="text-slate-500 font-semibold">{t.pricebook.price_not_set}</span>
                      ) : (
                        <span className="text-emerald-700">{formatPrice(item.price)} {t.pricebook.currency_symbol}</span>
                      )}
                      <span className="block text-xs font-normal text-slate-500">/ {unitLabel(item.unit)}</span>
                    </span>
                  </button>
                  {!item.is_archived && (
                    <button
                      type="button"
                      aria-label={`edit-price-item-${item.id}`}
                      title={t.common.edit}
                      onClick={() => (editing?.id === item.id && showForm ? closeForm() : openEdit(item))}
                      className="shrink-0 min-h-11 min-w-11 flex items-center justify-center rounded-xl bg-blue-50 text-blue-700 hover:bg-blue-100 transition"
                    >
                      <span aria-hidden="true">✏️</span>
                    </button>
                  )}
                </div>

                {showForm && editing?.id === item.id && (
                  <div className="px-2 pb-2">
                    <PriceItemForm ref={formRef} initialItem={item} onCancel={closeForm} onSaved={handleFormSaved} />
                  </div>
                )}

                {open && (
                  <div aria-label={`price-item-details-${item.id}`} className="px-3 pb-3 space-y-2 border-t border-slate-100 pt-2">
                    {item.quality_level && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-800 font-medium inline-block">
                        {qualityLabel(item.quality_level)}
                      </span>
                    )}
                    <p className="text-xs text-slate-500">
                      {categoryLabel(item.category)}
                      {item.price_scope !== 'LABOR' && <> · {scopeLabel(item.price_scope)}</>}
                    </p>
                    {item.is_archived ? (
                      <button
                        type="button"
                        aria-label={`restore-price-item-${item.id}`}
                        onClick={() => void handleRestore(item)}
                        className="min-h-11 w-full px-3 py-2 text-xs rounded-lg bg-emerald-50 text-emerald-700 font-medium hover:bg-emerald-100 transition"
                      >
                        <Ico>♻️</Ico>{t.common.restore}
                      </button>
                    ) : (
                      <button
                        type="button"
                        aria-label={`archive-price-item-${item.id}`}
                        onClick={() => void handleArchive(item)}
                        className="min-h-11 w-full px-3 py-2 text-xs rounded-lg bg-orange-50 text-orange-700 font-medium hover:bg-orange-100 transition"
                      >
                        <Ico>🗃️</Ico>{t.common.archive}
                      </button>
                    )}
                    <PriceBookMarket
                      itemId={item.id}
                      entry={evidence[item.id]}
                      unitLabel={unitLabel}
                      itemUnit={item.unit}
                      onUseReference={item.price === null && !item.is_archived ? (price) => void takeReference(item, price) : undefined}
                      useBusy={referenceBusy === item.id}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
        </>
      )}
    </section>
  );
}