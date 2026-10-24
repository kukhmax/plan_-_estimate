import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { fetchClients } from '../api/clients';
import {
  createQuickEstimate,
  fetchQuickEstimateOptions,
  QuickEstimateOptions,
  QuickEstimateRequestError,
} from '../api/quickEstimate';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { ClientType } from '../types/client';
import { PriceItem } from '../types/priceItem';
import { resolveDisplayName } from '../utils/priceItemName';
import { DimensionInput } from './DimensionInput';
import { Ico } from './Ico';
import { StarterPricesSheet } from './StarterPricesSheet';

interface QuickEstimateProps {
  /** The estimate was made: the object opens on its estimates. */
  onDone: (projectId: string) => void;
  onClose: () => void;
  backSuspended?: boolean;
  onOpenPricebook?: () => void;
}

interface RoomDraft {
  key: number;
  name: string;
  length: string;
  width: string;
  height: string;
}

const S_LEVELS: QualityLevelValue[] = ['S1', 'S2', 'S3', 'S4'];
const Q_LEVELS: QualityLevelValue[] = ['Q1', 'Q2', 'Q3', 'Q4'];
const substrateKey: Record<SubstrateValue, string> = {
  CONCRETE: 'substrate_concrete',
  GYPSUM_PLASTER: 'substrate_gypsum_plaster',
  CEMENT_LIME_PLASTER: 'substrate_cement_lime_plaster',
  GYPSUM_BOARD: 'substrate_gypsum_board',
  PAINTED: 'substrate_painted',
  OTHER: 'substrate_other',
};

function levelsFor(substrate: SubstrateValue): QualityLevelValue[] {
  return substrate === 'GYPSUM_BOARD' ? Q_LEVELS : S_LEVELS;
}

function clientLabel(client: ClientType): string {
  if (client.client_type === 'COMPANY') return client.company_name ?? '—';
  return [client.first_name, client.last_name].filter(Boolean).join(' ') || '—';
}

let roomKey = 0;
const newRoom = (name = '', height = ''): RoomDraft => ({ key: ++roomKey, name, length: '', width: '', height });

const inputClass = 'w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm';

/**
 * "Szybka wycena" (V2-4): a client, an address, rooms by three sizes, the works ticked, the class -- and the server makes the object, the rooms with
 * their plans and a draft estimate in one request. The doors and windows are not deducted (said on the screen); the estimate opens on the usual
 * screen, where it is finished and issued.
 */
export function QuickEstimate({ onDone, onClose, backSuspended = false, onOpenPricebook }: QuickEstimateProps) {
  const { t } = useI18n();
  const text = t.quick;
  const [options, setOptions] = useState<QuickEstimateOptions | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [clients, setClients] = useState<ClientType[]>([]);
  const [clientMode, setClientMode] = useState<'existing' | 'new'>('new');
  const [clientId, setClientId] = useState('');
  const [clientName, setClientName] = useState('');
  const [clientPhone, setClientPhone] = useState('');
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('');
  const [rooms, setRooms] = useState<RoomDraft[]>(() => [newRoom(text.rooms_names[0])]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [ceiling, setCeiling] = useState(true); // a room is finished with its ceiling: ticked from the start (V2-4, owner's check)
  const [substrate, setSubstrate] = useState<SubstrateValue>('GYPSUM_PLASTER');
  const [quality, setQuality] = useState<QualityLevelValue>('S2');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pricesOpen, setPricesOpen] = useState(false);

  useTelegramBackButton(!backSuspended, onClose);

  const loadOptions = useCallback(async (first: boolean) => {
    try {
      const found = await fetchQuickEstimateOptions();
      setOptions(found);
      if (first) {
        setChecked(new Set(found.works.filter((work) => work.default_on).map((work) => work.code)));
        setSubstrate(found.default_substrate);
        setQuality(found.default_quality);
      }
    } catch {
      setLoadFailed(true);
    }
  }, []);

  useEffect(() => {
    void loadOptions(true);
    void Promise.resolve()
      .then(() => fetchClients())
      .then((found) => {
        setClients(found.items);
        if (found.items.length > 0) setClientMode('existing');
      })
      .catch(() => setClients([]));
  }, [loadOptions]);

  const itemByCode = useMemo(() => new Map((options?.items ?? []).map((item) => [item.code, item])), [options]);
  const chosenWorks = (options?.works ?? []).filter((work) => checked.has(work.code));
  // the price rows that the chosen works will use and that have no price yet
  const unpriced: PriceItem[] = useMemo(() => {
    const rows: PriceItem[] = [];
    for (const work of chosenWorks) {
      for (const code of ceiling ? [work.code, work.ceiling_code] : [work.code]) {
        const item = itemByCode.get(code);
        if (item && item.price === null && !rows.includes(item)) rows.push(item);
      }
    }
    return rows;
  }, [chosenWorks, ceiling, itemByCode]);

  const setRoom = (key: number, patch: Partial<RoomDraft>) => setRooms((current) => current.map((room) => (room.key === key ? { ...room, ...patch } : room)));

  const changeSubstrate = (value: SubstrateValue) => {
    setSubstrate(value);
    if (!levelsFor(value).includes(quality)) setQuality(value === 'GYPSUM_BOARD' ? 'Q2' : 'S2');
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (clientMode === 'existing' ? clientId === '' : clientName.trim() === '') return setError(text.need_client);
    if (address.trim() === '' || city.trim() === '') return setError(text.need_address);
    if (rooms.some((room) => room.name.trim() === '' || !(Number(room.length) > 0) || !(Number(room.width) > 0) || !(Number(room.height) > 0))) {
      return setError(text.need_room);
    }
    if (chosenWorks.length === 0) return setError(text.need_work);
    setBusy(true);
    try {
      const made = await createQuickEstimate({
        ...(clientMode === 'existing' ? { client_id: clientId } : { client_name: clientName.trim(), ...(clientPhone.trim() ? { client_phone: clientPhone.trim() } : {}) }),
        address: address.trim(),
        city: city.trim(),
        rooms: rooms.map((room) => ({ name: room.name.trim(), length: room.length, width: room.width, height: room.height })),
        work_codes: chosenWorks.map((work) => work.code),
        include_ceiling: ceiling,
        substrate,
        quality_target: quality,
      });
      onDone(made.project_id);
    } catch (failure) {
      const code = failure instanceof QuickEstimateRequestError ? failure.code : null;
      const known = code ? (text as unknown as Record<string, string>)[`err_${code}`] : undefined;
      setError(known ?? text.failed);
      setBusy(false);
    }
  };

  return (
    <form aria-label="quick-estimate-form" onSubmit={submit} className="w-full space-y-4">
      <p className="text-sm text-slate-600 break-words">{text.intro}</p>
      {loadFailed && <p role="alert" className="text-sm text-red-600 break-words">{text.load_failed}</p>}

      <section aria-label="quick-client" className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
        <h3 className="font-semibold text-slate-900">{text.client_section}</h3>
        {clients.length > 0 && (
          <div className="grid grid-cols-2 gap-2">
            {(['existing', 'new'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                aria-label={`quick-client-${mode}`}
                aria-pressed={clientMode === mode}
                onClick={() => setClientMode(mode)}
                className={`min-h-11 px-2 text-sm rounded-xl border font-semibold break-words ${clientMode === mode ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-300 text-slate-800'}`}
              >
                {mode === 'existing' ? text.client_existing : text.client_new}
              </button>
            ))}
          </div>
        )}
        {clientMode === 'existing' && clients.length > 0 ? (
          <select aria-label="quick-client-select" value={clientId} onChange={(event) => setClientId(event.target.value)} className={inputClass}>
            <option value="">{text.client_pick}</option>
            {clients.map((client) => (
              <option key={client.id} value={client.id}>{clientLabel(client)}</option>
            ))}
          </select>
        ) : (
          <>
            <input aria-label="quick-client-name" placeholder={text.client_name} maxLength={255} value={clientName} onChange={(event) => setClientName(event.target.value)} className={inputClass} />
            <input aria-label="quick-client-phone" type="tel" inputMode="tel" placeholder={text.client_phone} maxLength={50} value={clientPhone} onChange={(event) => setClientPhone(event.target.value)} className={inputClass} />
          </>
        )}
        <input aria-label="quick-address" placeholder={text.address} maxLength={512} value={address} onChange={(event) => setAddress(event.target.value)} className={inputClass} />
        <input aria-label="quick-city" placeholder={text.city} maxLength={255} value={city} onChange={(event) => setCity(event.target.value)} className={inputClass} />
      </section>

      <section aria-label="quick-rooms" className="space-y-3">
        <h3 className="font-semibold text-slate-900">{text.rooms_section}</h3>
        {rooms.map((room, index) => (
          <div key={room.key} aria-label={`quick-room-${index}`} className="pe-card rounded-2xl p-3 shadow-sm space-y-2">
            <input aria-label={`quick-room-name-${index}`} placeholder={text.room_name} maxLength={255} value={room.name} onChange={(event) => setRoom(room.key, { name: event.target.value })} className={inputClass} />
            <div className="flex flex-wrap gap-1.5">
              {text.rooms_names.map((preset) => (
                <button key={preset} type="button" onClick={() => setRoom(room.key, { name: preset })} className="min-h-11 px-3 text-xs rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-100">
                  {preset}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-2">
              {([['length', text.length], ['width', text.width], ['height', text.height]] as const).map(([field, label]) => (
                <div key={field} className="min-w-0">
                  <label className="block text-xs text-slate-500 mb-1 break-words">{label}</label>
                  <DimensionInput
                    aria-label={`quick-room-${field}-${index}`}
                    placeholder={field === 'height' ? '260' : '500'}
                    value={room[field]}
                    onValueChange={(meters) => setRoom(room.key, { [field]: meters })}
                    className={inputClass}
                  />
                </div>
              ))}
            </div>
            {rooms.length > 1 && (
              <button type="button" aria-label={`quick-room-remove-${index}`} onClick={() => setRooms((current) => current.filter((row) => row.key !== room.key))} className="w-full min-h-11 text-sm rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-100">
                <Ico>🗑️</Ico>{text.remove_room}
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          aria-label="quick-room-add"
          onClick={() => setRooms((current) => [...current, newRoom('', current[current.length - 1]?.height ?? '')])}
          className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-slate-300 text-slate-800 hover:bg-slate-100"
        >
          <Ico>➕</Ico>{text.add_room}
        </button>
      </section>

      <section aria-label="quick-works" className="pe-card rounded-2xl p-4 shadow-sm space-y-2">
        <h3 className="font-semibold text-slate-900">{text.works_section}</h3>
        {options?.works.map((work) => {
          const item = itemByCode.get(work.code);
          const pending = item?.price === null || (ceiling && itemByCode.get(work.ceiling_code)?.price === null);
          return (
            <label key={work.code} className="flex items-start gap-3 min-h-11 py-1 text-sm text-slate-900 cursor-pointer">
              <input
                type="checkbox"
                aria-label={`quick-work-${work.code}`}
                checked={checked.has(work.code)}
                onChange={(event) => setChecked((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.add(work.code);
                  else next.delete(work.code);
                  return next;
                })}
                className="mt-0.5 h-6 w-6 shrink-0"
              />
              <span className="min-w-0 flex-1 break-words">
                {item ? resolveDisplayName(item, t as unknown as Record<string, unknown>) : work.code}
                {pending && <span className="ml-2 text-xs font-medium text-amber-700">{text.no_price}</span>}
              </span>
            </label>
          );
        })}
        <label className="flex items-center gap-3 min-h-11 py-1 text-sm font-semibold text-slate-900 cursor-pointer border-t border-slate-100 pt-2">
          <input type="checkbox" aria-label="quick-ceiling" checked={ceiling} onChange={(event) => setCeiling(event.target.checked)} className="h-6 w-6 shrink-0" />
          <span className="min-w-0 break-words">{text.ceiling_too}</span>
        </label>
        {unpriced.length > 0 && (
          <button type="button" aria-label="quick-set-prices" onClick={() => setPricesOpen(true)} className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-blue-600 text-white hover:bg-blue-700">
            <Ico>🏷️</Ico>{text.set_prices}
          </button>
        )}
      </section>

      <section aria-label="quick-class" className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
        <div>
          <label htmlFor="quick-substrate" className="block text-xs text-slate-500 mb-1">{text.substrate}</label>
          <select id="quick-substrate" aria-label="quick-substrate" value={substrate} onChange={(event) => changeSubstrate(event.target.value as SubstrateValue)} className={inputClass}>
            {(options?.substrates ?? [substrate]).map((value) => (
              <option key={value} value={value}>{(t.inspections as unknown as Record<string, string>)[substrateKey[value]]}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="quick-quality" className="block text-xs text-slate-500 mb-1">{text.quality}</label>
          <select id="quick-quality" aria-label="quick-quality" value={quality} onChange={(event) => setQuality(event.target.value as QualityLevelValue)} className={inputClass}>
            {levelsFor(substrate).map((level) => (
              <option key={level} value={level}>{t.pricebook.quality[level]}</option>
            ))}
          </select>
        </div>
        <p className="text-xs text-slate-500 break-words">{text.no_openings}</p>
      </section>

      {error && <p role="alert" aria-label="quick-error" className="text-sm text-red-600 font-medium break-words">{error}</p>}
      <div className="grid grid-cols-1 gap-2">
        <button type="submit" aria-label="quick-submit" disabled={busy || !options} className="w-full min-h-11 px-4 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50">
          <Ico>⚡</Ico>{busy ? text.submitting : text.submit}
        </button>
        <button type="button" aria-label="quick-cancel" onClick={onClose} className="w-full min-h-11 px-4 text-sm rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-100">
          <Ico>✖️</Ico>{text.cancel}
        </button>
      </div>
      {pricesOpen && (
        <StarterPricesSheet
          load={async () => ({ items: unpriced, total: unpriced.length })}
          onClose={() => setPricesOpen(false)}
          onSaved={() => void loadOptions(false)}
          onOpenAll={onOpenPricebook}
        />
      )}
    </form>
  );
}
