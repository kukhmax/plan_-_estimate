import { useEffect } from 'react';
import { useI18n } from '../hooks/useI18n';
import { PriceUnitValue } from '../types/priceItem';
import { PriceSource } from '../types/marketEvidence';
import { formatEvidenceDate } from '../utils/evidenceFormat';
import { formatPrice } from '../utils/priceFormat';

interface PriceSourceViewerProps {
  itemId: string;
  sources: PriceSource[];
  open: boolean;
  onClose: () => void;
  unitLabel: (value: PriceUnitValue) => string;
}

/**
 * Mobile bottom-sheet viewer for the market sources of one Price Book card.
 *
 * Sources are read-only research data and far too verbose for the card itself:
 * rendering them inline pushed the owner price out of view on a phone. They are
 * shown here instead, one sheet at a time, with the Price Book position kept
 * intact underneath.
 */
export function PriceSourceViewer({
  itemId,
  sources,
  open,
  onClose,
  unitLabel,
}: PriceSourceViewerProps) {
  const { t } = useI18n();

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

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
      role="dialog"
      aria-modal="true"
      aria-label={`price-sources-viewer-${itemId}`}
      className="fixed inset-0 z-50 flex items-end justify-center"
      onClick={onClose}
    >
      <div
        aria-hidden
        className="absolute inset-0"
        style={{ backgroundColor: 'rgba(0, 0, 0, 0.45)' }}
      />
      <div
        onClick={(event) => event.stopPropagation()}
        className="relative w-full max-w-md max-h-[85vh] overflow-y-auto rounded-t-2xl p-4 space-y-3"
        style={{
          backgroundColor: 'var(--tg-theme-secondary-bg-color)',
          color: 'var(--tg-theme-text-color)',
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold break-words">
            {t.pricebook.market.viewer_title}
          </h3>
          <button
            type="button"
            aria-label={`close-price-sources-${itemId}`}
            onClick={onClose}
            className="min-h-11 min-w-11 flex-shrink-0 text-sm font-medium rounded-xl px-3 border"
            style={{
              borderColor: 'var(--tg-control-border-color, rgba(0, 0, 0, 0.12))',
              color: 'var(--tg-theme-link-color)',
            }}
          >
            {t.common.close}
          </button>
        </div>

        <ul aria-label={`price-item-sources-${itemId}`} className="space-y-2">
          {sources.map((source, index) => (
            <li
              key={source.id}
              aria-label={`price-item-source-${itemId}-${index}`}
              className="w-full rounded-xl border border-slate-200 p-3 text-xs space-y-1"
              style={{ backgroundColor: 'var(--tg-theme-bg-color, #ffffff)' }}
            >
              <p className="font-semibold break-words">{source.source_name}</p>
              <p style={{ color: 'var(--tg-theme-hint-color)' }}>
                <span>{sourceTypeLabel(source)}</span>
                {source.source_region && <span> · {source.source_region}</span>}
              </p>
              {quoteText(source) && (
                <p className="font-semibold">
                  {quoteText(source)} {currency}
                  {quoteUnit(source)}
                </p>
              )}
              {source.note && (
                <p className="break-words whitespace-pre-line" style={{ color: 'var(--tg-theme-hint-color)' }}>
                  {source.note}
                </p>
              )}
              <p style={{ color: 'var(--tg-theme-hint-color)' }}>
                {t.pricebook.market.checked}: {formatEvidenceDate(source.checked_at)}
              </p>
              {source.source_url && (
                <a
                  href={source.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`price-item-source-link-${itemId}-${index}`}
                  className="inline-flex min-h-11 items-center font-medium break-all"
                  style={{ color: 'var(--tg-theme-link-color)' }}
                >
                  {t.pricebook.market.open_source}
                </a>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}