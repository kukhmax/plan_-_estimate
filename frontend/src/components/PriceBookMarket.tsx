import { useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { MarketEvidenceEntry } from '../hooks/useMarketEvidence';
import { PriceUnitValue } from '../types/priceItem';
import { formatEvidenceDate } from '../utils/evidenceFormat';
import { formatPrice } from '../utils/priceFormat';
import { PriceSourceViewer } from './PriceSourceViewer';

interface PriceBookMarketProps {
  itemId: string;
  entry: MarketEvidenceEntry | undefined;
  unitLabel: (value: PriceUnitValue) => string;
}

/**
 * Compact, secondary market evidence block for one Price Book card (Stage 9E.6B).
 *
 * The owner's working price stays the only primary value; the market range below
 * it is read-only supporting research data and never influences the editable
 * price. Sources themselves open in a dedicated mobile bottom sheet (Stage
 * 9E.8) so the card stays short and the owner price stays in view. Evidence that
 * is loading (compact muted line), missing (small "no market data" state), or
 * failed (collapses silently) never breaks the card.
 */
export function PriceBookMarket({ itemId, entry, unitLabel }: PriceBookMarketProps) {
  const { t } = useI18n();
  const [viewerOpen, setViewerOpen] = useState(false);

  if (!entry || entry.status === 'error') return null;

  if (entry.status === 'loading') {
    return (
      <div
        aria-label={`price-item-market-loading-${itemId}`}
        className="mt-2 pt-2 border-t border-slate-100 text-xs text-slate-400"
      >
        {t.pricebook.market.market}: {t.pricebook.market.loading}
      </div>
    );
  }

  const reference = entry.references?.[0];
  if (!reference) {
    return (
      <div
        aria-label={`price-item-market-empty-${itemId}`}
        className="mt-2 pt-2 border-t border-slate-100 text-xs text-slate-400"
      >
        {t.pricebook.market.market}: {t.pricebook.market.no_evidence}
      </div>
    );
  }

  const currency = t.pricebook.currency_symbol;

  return (
    <div
      aria-label={`price-item-market-${itemId}`}
      className="mt-2 pt-2 border-t border-slate-100 space-y-1"
    >
      <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className="text-[10px] uppercase tracking-wide text-slate-400 font-medium">
          {t.pricebook.market.market}:
        </span>
        <span className="text-sm font-semibold text-slate-700">
          {formatPrice(reference.market_min)}–{formatPrice(reference.market_max)}
          <span className="font-normal text-slate-400">
            {' '}
            {currency} / {unitLabel(reference.unit)}
          </span>
        </span>
        <span className="text-xs text-slate-400">
          {t.pricebook.market.checked}: {formatEvidenceDate(reference.checked_at)}
        </span>
      </div>

      {reference.reference_price !== null && (
        <p className="text-xs text-slate-500">
          {t.pricebook.market.reference}: {formatPrice(reference.reference_price)} {currency}
        </p>
      )}

      <button
        type="button"
        aria-expanded={viewerOpen}
        aria-label={`price-item-sources-toggle-${itemId}`}
        onClick={() => setViewerOpen((v) => !v)}
        className="min-h-11 flex items-center gap-1 -ml-1 px-1 text-sm text-blue-600 font-medium hover:underline"
      >
        {t.pricebook.market.sources} ({reference.sources.length})
        <span aria-hidden>{viewerOpen ? '' : '▾'}</span>
      </button>

      <PriceSourceViewer
        itemId={itemId}
        sources={reference.sources}
        open={viewerOpen}
        onClose={() => setViewerOpen(false)}
        unitLabel={unitLabel}
      />
    </div>
  );
}