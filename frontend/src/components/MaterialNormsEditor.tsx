import { useCallback, useState } from 'react';
import { ApiError } from '../api/http';
import { fetchPriceItems } from '../api/priceItems';
import { fetchNorms, updateNorm } from '../api/materials';
import { useI18n } from '../hooks/useI18n';
import { useConnection } from '../offline/connection';
import type { PriceItem } from '../types/priceItem';
import type { MaterialNorm, MaterialPackage } from '../types/materials';
import { resolveKey } from '../utils/i18nKeys';
import { formatPlain, toInput } from '../utils/paymentFormat';
import { Ico } from './Ico';
import { fieldClass, labelClass, primaryButton, secondaryButton } from './paymentUi';
import { VoiceInput } from './VoiceInput';

type ItemChoice = Pick<PriceItem, 'id' | 'code' | 'name_key' | 'display_name' | 'unit'>;

function itemName(item: { display_name: string | null; name_key: string | null; code: string }, t: unknown): string {
  return item.display_name ?? (item.name_key ? resolveKey(t, item.name_key) : item.code);
}

/**
 * V2-11 — the owner's reference of consumption norms: the numbers (waste, consumption, size of a pack) and the materials (their name and the price-book item that gives the price). The
 * starting numbers are a guide that the owner corrects; every row can go back to its starting value. Closed until opened. Online only.
 */
export function MaterialNormsEditor({ onChanged }: { onChanged: () => void }) {
  const { t } = useI18n();
  const text = t.materials;
  const { offline } = useConnection();
  const [open, setOpen] = useState(false);
  const [norms, setNorms] = useState<MaterialNorm[] | null>(null);
  const [items, setItems] = useState<ItemChoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [group, setGroup] = useState<MaterialPackage | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const [rows, list] = await Promise.all([fetchNorms(), fetchPriceItems({ archived: 'active' })]);
      setNorms(rows);
      setItems(list.items);
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && norms === null) void load();
  };

  const replace = (row: MaterialNorm) => {
    setNorms((current) => (current ? current.map((n) => (n.id === row.id ? row : n)) : current));
    onChanged();
  };

  return (
    <section aria-label="material-norms" className="w-full min-w-0 space-y-3">
      <button
        type="button"
        aria-label="material-norms-toggle"
        aria-expanded={open}
        onClick={toggle}
        className="w-full min-h-11 px-4 py-2 flex flex-wrap items-center justify-between gap-x-3 text-left text-base font-bold text-slate-900 pe-card rounded-2xl shadow-sm"
      >
        <span className="break-words"><Ico>📐</Ico>{text.norms_title}</span>
        <span className="text-sm font-semibold text-blue-700">{open ? text.norms_hide : text.norms_show}</span>
      </button>
      {open && (
        <div className="space-y-3">
          <p className="text-xs text-[var(--tg-theme-hint-color)] break-words">{text.norms_intro}</p>
          {loading && norms === null && <p className="text-sm text-slate-500 text-center py-3">{text.loading}</p>}
          {!loading && loadFailed && (
            <div className="space-y-2">
              <p role="alert" className="text-sm text-red-600 break-words">{text.load_error}</p>
              <button type="button" aria-label="material-norms-retry" onClick={() => void load()} className={primaryButton}><Ico>🔄</Ico>{text.retry}</button>
            </div>
          )}
          {norms && (['TILE', 'DRYWALL'] as const).map((pkg) => (
            <div key={pkg} className="space-y-2">
              <button
                type="button"
                aria-label={`material-norms-group-${pkg}`}
                aria-expanded={group === pkg}
                onClick={() => setGroup(group === pkg ? null : pkg)}
                className="w-full min-h-11 px-4 py-2 flex items-center justify-between gap-3 text-left text-sm font-semibold text-slate-900 pe-card rounded-2xl"
              >
                <span>{pkg === 'TILE' ? text.group_TILE : text.group_DRYWALL}</span>
                <span className="text-blue-700">{group === pkg ? text.hide : text.show}</span>
              </button>
              {group === pkg && (
                <ul aria-label={`material-norms-list-${pkg}`} className="space-y-2 min-w-0">
                  {norms.filter((n) => n.package === pkg).map((n) => (
                    <NormRow key={`${n.id}-${n.value}-${n.name}-${n.price_item?.id ?? ''}`} norm={n} items={items} offline={offline} onSaved={replace} />
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function NormRow({ norm, items, offline, onSaved }: { norm: MaterialNorm; items: ItemChoice[]; offline: boolean; onSaved: (row: MaterialNorm) => void }) {
  const { t } = useI18n();
  const text = t.materials;
  const [value, setValue] = useState(toInput(norm.value));
  const [name, setName] = useState(norm.name);
  const [itemId, setItemId] = useState(norm.price_item?.id ?? '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const isNumber = norm.kind === 'PARAM';
  const label = isNumber ? ((text.norms as Record<string, string>)[norm.code] ?? norm.code) : norm.name;
  const choices = items.filter((item) => item.unit === norm.billing_unit);
  const kept = norm.price_item && !choices.some((item) => item.id === norm.price_item?.id) ? [norm.price_item, ...choices] : choices;
  const changed = isNumber
    ? value.replace(',', '.') !== (norm.value ?? '')
    : name.trim() !== norm.name || itemId !== (norm.price_item?.id ?? '');
  const differsFromStart = isNumber ? norm.value !== norm.default_value : norm.price_item !== null || norm.name !== norm.default_name;

  const send = async (changes: Parameters<typeof updateNorm>[1]) => {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    try {
      onSaved(await updateNorm(norm.id, changes));
    } catch (err) {
      const code = err instanceof ApiError ? err.code : undefined;
      const known = code ? (text as Record<string, unknown>)[`err_${code}`] : undefined;
      setMessage({ kind: 'error', text: typeof known === 'string' ? known : text.save_error });
      setBusy(false);
    }
  };

  const save = () => {
    if (isNumber) {
      const cleaned = value.trim().replace(',', '.');
      if (!/^\d+(\.\d{1,3})?$/.test(cleaned)) {
        setMessage({ kind: 'error', text: text.err_NORM_OUT_OF_RANGE });
        return;
      }
      void send({ value: cleaned });
    } else {
      void send({ name: name.trim() !== '' ? name.trim() : undefined, price_item_id: itemId === '' ? null : itemId });
    }
  };

  return (
    <li aria-label={`material-norm-${norm.code}`} className="pe-card rounded-2xl p-3 shadow-sm space-y-2">
      <p className="text-sm font-semibold text-slate-900 break-words">{label}</p>
      {isNumber ? (
        <div>
          <label htmlFor={`norm-${norm.code}`} className={labelClass}>{text.value_label} ({norm.unit_text})</label>
          <VoiceInput name={`norm-${norm.code}`} mode="plain" onValue={(v) => setValue(v.replace('.', ','))}>
            <input id={`norm-${norm.code}`} aria-label={`norm-${norm.code}`} inputMode="decimal" autoComplete="off" value={value} onChange={(event) => setValue(event.target.value)} className={`${fieldClass} min-w-0 flex-1`} />
          </VoiceInput>
          <p className="text-xs text-slate-500 mt-1 break-words">{text.default_is.replace('{v}', formatPlain(norm.default_value))}</p>
        </div>
      ) : (
        <>
          <div>
            <label htmlFor={`norm-name-${norm.code}`} className={labelClass}>{text.name_label}</label>
            <input id={`norm-name-${norm.code}`} aria-label={`norm-name-${norm.code}`} maxLength={120} value={name} onChange={(event) => setName(event.target.value)} className={fieldClass} />
          </div>
          <div>
            <label htmlFor={`norm-item-${norm.code}`} className={labelClass}>{text.price_item_label}</label>
            <select id={`norm-item-${norm.code}`} aria-label={`norm-item-${norm.code}`} value={itemId} onChange={(event) => setItemId(event.target.value)} className={fieldClass}>
              <option value="">{text.price_item_none}</option>
              {kept.map((item) => (
                <option key={item.id} value={item.id}>{itemName(item, t)}</option>
              ))}
            </select>
          </div>
        </>
      )}
      {message && <p role={message.kind === 'error' ? 'alert' : 'status'} className={`text-xs break-words ${message.kind === 'error' ? 'text-red-600' : 'text-emerald-700'}`}>{message.text}</p>}
      <div className="grid grid-cols-2 gap-2">
        <button type="button" aria-label={`norm-save-${norm.code}`} disabled={busy || offline || !changed} onClick={save} className="w-full min-h-11 px-2 py-2 text-sm leading-tight rounded-xl bg-blue-600 text-white font-semibold break-words disabled:opacity-50">
          <Ico>💾</Ico>{text.save}
        </button>
        <button
          type="button"
          aria-label={`norm-reset-${norm.code}`}
          disabled={busy || offline || !differsFromStart}
          onClick={() => void send({ reset: true })}
          className={`${secondaryButton} !px-2 leading-tight`}
        >
          <Ico>↩️</Ico>{text.reset}
        </button>
      </div>
    </li>
  );
}
