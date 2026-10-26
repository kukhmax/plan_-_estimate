import { useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import { refreshTrades, useTrades } from '../hooks/useTrades';
import type { TradeKey } from '../types/trades';

/**
 * V2-13 — the packages of professions the owner works in (checkboxes in the profile). Every tap is saved at once; the price book, the plan of a wall, the materials and the points of
 * a room then offer only these (nothing is deleted: what already exists stays). While the answer of the server is not known nothing can be changed and nothing is hidden.
 */
export function TradesPicker() {
  const { t } = useI18n();
  const text = t.trades;
  const trades = useTrades();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async (key: TradeKey) => {
    if (busy) return;
    const next = trades.trades.map((trade) => trade.key).filter((k) => (k === key ? !trades.isEnabled(key) : trades.isEnabled(k)));
    setBusy(true);
    setError(null);
    try {
      await trades.save(next);
    } catch {
      setError(text.save_failed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="trades-picker" className="mt-4 space-y-2 rounded-xl border p-3" style={{ borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))' }}>
      <h3 className="text-sm font-bold break-words">{text.title}</h3>
      <p className="text-xs break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.intro}</p>
      {!trades.known && (
        <div className="space-y-2">
          <p className="text-xs break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.loading}</p>
          <button type="button" aria-label="trades-retry" onClick={() => void refreshTrades()} className="min-h-11 w-full rounded-xl border text-sm font-semibold">
            {t.auth.retry}
          </button>
        </div>
      )}
      {trades.known && (
        <ul className="space-y-1">
          {trades.trades.map((trade) => (
            <li key={trade.key}>
              <label className="flex min-h-11 items-start gap-3 py-1">
                <input
                  type="checkbox"
                  aria-label={`trade-${trade.key}`}
                  className="mt-0.5 h-5 w-5 shrink-0"
                  checked={trades.isEnabled(trade.key)}
                  disabled={busy}
                  onChange={() => void toggle(trade.key)}
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium break-words">{text.names[trade.key]}</span>
                  <span className="block text-xs break-words" style={{ color: 'var(--tg-theme-hint-color)' }}>{text.hints[trade.key]}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert" className="text-xs font-medium text-red-700 break-words">{error}</p>}
    </section>
  );
}
