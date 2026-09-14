import { useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { MarketEvidenceEntry } from '../hooks/useMarketEvidence';
import { PriceUnitValue } from '../types/priceItem';
import { PriceSource } from '../types/marketEvidence';
import { formatEvidenceDate } from '../utils/evidenceFormat';
import { formatPrice } from '../utils/priceFormat';

interface PriceBookMarketProps {
  itemId: string;
  entry: MarketEvidenceEntry | undefined;
  unitLabel: (value: PriceUnitValue) => string;
}

/**
 * Compact, secondary market evidence block for one Price Book card (Stage 9E.6B).
 *
 * The owner's working price stays the only primary value; the market range and
 * sources below it are read-only supporting research data and never influence
 * the editable price. Evidence that is loading (compact muted line), missing
 * (small "no market data" state), or failed (collapses silently) never breaks
 * the card.
 */
export function PriceBookMarket({ itemId, entry, unitLabel }: PriceBookMarketProps) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);

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
  const sourceTypeLabel = (source: PriceSource): string =>
    t.pricebook.market.source_type[source.source_type];

  const quoteText = (source: PriceSource): string | null => {
    if (source.quoted_price_single !== null) return formatPrice(source.quoted_price_single);
    if (source.quoted_price_min !== null && source.quoted_price_max !== null) {
      return `${formatPrice(source.quoted_price_min)}–${formatPrice(source.quoted_price_max)}`;
    }
    return null;
  };

  const quoteUnit = (source: PriceSource): string | null =>
    source.quoted_unit ? ` / ${unitLabel(source.quoted_unit)}` : null;

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
        aria-expanded={expanded}
        aria-label={`price-item-sources-toggle-${itemId}`}
        onClick={() => setExpanded((v) => !v)}
        className="min-h-11 flex items-center gap-1 -ml-1 px-1 text-sm text-blue-600 font-medium hover:underline"
      >
        {t.pricebook.market.sources} ({reference.sources.length})
        <span aria-hidden>{expanded ? '▴' : '▾'}</span>
      </button>

      {expanded && (
        <ul aria-label={`price-item-sources-${itemId}`} className="space-y-2 pt-1">
          {reference.sources.map((source, index) => (
            <li
              key={source.id}
              aria-label={`price-item-source-${itemId}-${index}`}
              className="rounded-xl bg-slate-50 border border-slate-200 p-2.5 text-xs space-y-1"
            >
              <p className="font-semibold text-slate-800 break-words">{source.source_name}</p>
              <p className="text-slate-500">
                <span>{sourceTypeLabel(source)}</span>
                {source.source_region && <span> · {source.source_region}</span>}
              </p>
              {quoteText(source) && (
                <p className="font-semibold text-slate-700">
                  {quoteText(source)} {currency}
                  {quoteUnit(source)}
                </p>
              )}
              {source.note && (
                <p className="text-slate-500 break-words whitespace-pre-line">{source.note}</p>
              )}
              <p className="text-slate-500">
                {t.pricebook.market.checked}: {formatEvidenceDate(source.checked_at)}
              </p>
              {source.source_url && (
                <a
                  href={source.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`price-item-source-link-${itemId}-${index}`}
                  className="inline-flex min-h-11 items-center text-blue-600 font-medium"
                >
                  {t.pricebook.market.open_source}
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}