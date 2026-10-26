import { useCallback, useEffect, useState } from 'react';
import { fetchStatement } from '../api/materials';
import { useI18n } from '../hooks/useI18n';
import type { Statement } from '../types/materials';
import { buyWord, calcSummary, needWord } from '../utils/materialsFormat';
import { formatMoney } from '../utils/paymentFormat';
import { Ico } from './Ico';
import { MaterialNormsEditor } from './MaterialNormsEditor';
import { primaryButton } from './paymentUi';

/**
 * V2-11 — the statement of the materials of an object: what to buy over all its calculations (the packs counted once over the sum, the price of the price-book item a material is tied
 * to), the calculations by room and the owner's norms. The screen shows what the server sent and counts nothing.
 */
export function MaterialsScreen({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const text = t.materials;
  const [statement, setStatement] = useState<Statement | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      setStatement(await fetchStatement(projectId));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div aria-label="materials-screen" className="w-full min-w-0 mt-4 space-y-4">
      <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.statement_intro}</p>
      {loading && <p className="text-sm text-slate-500 text-center py-3">{text.loading}</p>}
      {!loading && failed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
          <button type="button" aria-label="materials-retry" onClick={() => void load()} className={primaryButton}><Ico>🔄</Ico>{text.retry}</button>
        </div>
      )}
      {statement && (
        <>
          {statement.totals.length === 0 ? (
            <p aria-label="materials-empty" className="text-sm text-slate-500 text-center py-3 break-words">{text.no_calcs}</p>
          ) : (
            <section aria-label="materials-totals" className="space-y-2">
              <h2 className="text-base font-bold text-slate-900">{text.totals_title}</h2>
              <ul className="space-y-2 min-w-0">
                {statement.totals.map((line) => (
                  <li key={line.code} aria-label={`material-total-${line.code}`} className="pe-card rounded-2xl p-3 shadow-sm space-y-1">
                    <div className="flex items-start justify-between gap-3">
                      <p className="min-w-0 flex-1 text-sm font-semibold text-slate-900 break-words">{line.name}</p>
                      <p className="shrink-0 text-base font-bold text-slate-900 whitespace-nowrap">{buyWord(line, text)}</p>
                    </div>
                    <p className="text-xs text-slate-500 break-words">{needWord(line, text)}</p>
                    <p aria-label={`material-price-${line.code}`} className="text-xs text-slate-700 break-words">
                      {line.amount === null ? text.price_unset : `${text.unit_price.replace('{v}', formatMoney(line.unit_price)).replace('{unit}', line.billing_unit === 'M2' ? text.unit_m2 : text.unit_pcs)} = ${formatMoney(line.amount)}`}
                    </p>
                  </li>
                ))}
              </ul>
              <div aria-label="materials-amount" className="pe-card rounded-2xl p-3 shadow-sm space-y-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="text-sm text-slate-600">{text.amount_total}</span>
                  <span className="text-base font-bold text-slate-900">{statement.amount === null ? '—' : formatMoney(statement.amount)}</span>
                </div>
                {statement.unpriced > 0 && <p className="text-xs text-slate-500">{text.unpriced.replace('{n}', String(statement.unpriced))}</p>}
              </div>
            </section>
          )}
          {statement.calcs.length > 0 && (
            <section aria-label="materials-calcs" className="space-y-2">
              <h2 className="text-base font-bold text-slate-900">{text.calcs_title}</h2>
              <ul className="space-y-2 min-w-0">
                {statement.calcs.map((calc) => (
                  <li key={calc.id} className="pe-card rounded-2xl p-3 shadow-sm">
                    <p className="text-sm font-semibold text-slate-900 break-words">{calc.room_name}{calc.title ? ` · ${calc.title}` : ''}</p>
                    <p className="text-xs text-slate-600 break-words">{{ TILE: text.pkg_TILE, DRYWALL: text.pkg_DRYWALL, ELECTRIC: text.pkg_ELECTRIC, PLUMBING: text.pkg_PLUMBING }[calc.package]} · {calcSummary(calc, text)}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <MaterialNormsEditor onChanged={() => void load()} />
        </>
      )}
    </div>
  );
}
