import { useCallback, useEffect, useState } from 'react';
import { deleteExample, fetchExample, fetchStarterPrices } from '../api/onboarding';
import { useI18n } from '../hooks/useI18n';
import { Ico } from './Ico';
import { StarterPricesSheet } from './StarterPricesSheet';

interface ExampleBannerProps {
  /** The object that is open now: the banner shows only when it is the example object of the account. */
  projectId: string;
  /** The example was deleted: the screen leaves the object. */
  onRemoved: () => void;
  onOpenPricebook?: () => void;
}

/** "To jest przykładowy obiekt" (V2-3): on the example object only — how to delete it, and (while the starter prices are empty) how to set them. */
export function ExampleBanner({ projectId, onRemoved, onOpenPricebook }: ExampleBannerProps) {
  const { t } = useI18n();
  const text = t.onboarding;
  const [isExample, setIsExample] = useState(false);
  const [needsPrices, setNeedsPrices] = useState(false);
  const [pricesOpen, setPricesOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const readPrices = useCallback(() => {
    void Promise.resolve()
      .then(() => fetchStarterPrices())
      .then((found) => setNeedsPrices(found.items.some((item) => item.price === null)))
      .catch(() => setNeedsPrices(false));
  }, []);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve()
      .then(() => fetchExample())
      .then((found) => {
        if (cancelled) return;
        const mine = found.project_id === projectId;
        setIsExample(mine);
        if (mine) readPrices();
      })
      .catch(() => {
        if (!cancelled) setIsExample(false); // the banner is an extra: a failing request leaves the screen as it was
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, readPrices]);

  if (!isExample) return null;

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteExample();
      onRemoved();
    } catch {
      setError(text.example_remove_failed);
      setBusy(false);
    }
  };

  return (
    <section aria-label="example-banner" className="pe-card rounded-2xl border-2 border-amber-400 p-3 space-y-2">
      <p className="text-sm font-semibold text-slate-900 break-words"><Ico>🧪</Ico>{text.example_banner_title}</p>
      <p className="text-xs text-slate-600 break-words">{text.example_banner_text}</p>
      {needsPrices && (
        <button
          type="button"
          aria-label="example-set-prices"
          onClick={() => setPricesOpen(true)}
          className="w-full min-h-11 px-3 py-1 text-sm font-semibold rounded-xl bg-blue-600 text-white hover:bg-blue-700"
        >
          <Ico>🏷️</Ico>{text.prices_open}
        </button>
      )}
      {confirming ? (
        <div className="space-y-2">
          <p className="text-sm font-semibold text-slate-900 break-words">{text.example_remove_confirm}</p>
          <div className="flex gap-2">
            <button type="button" aria-label="example-remove-cancel" onClick={() => setConfirming(false)} className="flex-1 min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-300 text-slate-800 font-medium hover:bg-slate-100">
              <Ico>✖️</Ico>{t.common.cancel}
            </button>
            <button type="button" aria-label="example-remove-confirm" disabled={busy} onClick={() => void remove()} className="flex-1 min-h-11 px-3 py-1 text-sm rounded-xl bg-red-600 text-white font-semibold disabled:opacity-50">
              <Ico>🗑️</Ico>{text.example_remove_yes}
            </button>
          </div>
        </div>
      ) : (
        <button type="button" aria-label="example-remove" onClick={() => setConfirming(true)} className="w-full min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-300 text-slate-800 font-medium hover:bg-slate-100">
          <Ico>🗑️</Ico>{text.example_remove}
        </button>
      )}
      {error && <p role="alert" className="text-sm text-red-600 break-words">{error}</p>}
      {pricesOpen && <StarterPricesSheet onClose={() => setPricesOpen(false)} onSaved={readPrices} onOpenAll={onOpenPricebook} />}
    </section>
  );
}
