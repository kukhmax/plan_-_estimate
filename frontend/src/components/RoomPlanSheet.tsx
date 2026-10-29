import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchPriceItems } from '../api/priceItems';
import { fetchRooms } from '../api/rooms';
import { fetchRoomWorkPlan, RoomPlanRequestError, saveRoomWorkPlan } from '../api/roomWorkPlans';
import { fetchSurfaceWorkPlan } from '../api/workPlans';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { PriceCategoryValue, PriceItem } from '../types/priceItem';
import { RoomWorkPlanResponse, SurfacePlanState } from '../types/roomWorkPlan';
import { resolveDisplayName } from '../utils/priceItemName';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { Ico } from './Ico';
import { RoomPlanProcessPicker } from './RoomPlanProcessPicker';

interface RoomPlanSheetProps {
  projectId: string;
  roomId: string;
  onClose: () => void;
  /** The plan was saved and applied: the surfaces are read again. */
  onSaved: () => void;
}

// the plan of a room covers walls and the ceiling: the substrates of a floor are chosen on the floor
const SUBSTRATES: SubstrateValue[] = ['GYPSUM_PLASTER', 'CEMENT_LIME_PLASTER', 'CONCRETE', 'GYPSUM_BOARD', 'PAINTED', 'OTHER'];
const S_LEVELS: QualityLevelValue[] = ['S1', 'S2', 'S3', 'S4'];
const Q_LEVELS: QualityLevelValue[] = ['Q1', 'Q2', 'Q3', 'Q4'];
const ALL_LEVELS: QualityLevelValue[] = [...S_LEVELS, ...Q_LEVELS];
const substrateKey: Record<SubstrateValue, string> = {
  CONCRETE: 'substrate_concrete',
  GYPSUM_PLASTER: 'substrate_gypsum_plaster',
  CEMENT_LIME_PLASTER: 'substrate_cement_lime_plaster',
  GYPSUM_BOARD: 'substrate_gypsum_board',
  PAINTED: 'substrate_painted',
  OTHER: 'substrate_other',
  SCREED: 'substrate_screed',
  OLD_TILE: 'substrate_old_tile',
  WOOD_BOARDS: 'substrate_wood_boards',
};

function levelsFor(substrate: SubstrateValue): QualityLevelValue[] {
  if (substrate === 'GYPSUM_BOARD') return Q_LEVELS;
  if (substrate === 'PAINTED' || substrate === 'OTHER') return ALL_LEVELS;
  return S_LEVELS;
}

const inputClass = 'w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-sm';
const iconButton = 'shrink-0 min-h-11 min-w-11 rounded-xl border border-slate-300 text-slate-800 font-bold hover:bg-slate-100 disabled:opacity-30';

type Target = 'walls' | 'ceiling';

/**
 * "Plan pomieszczenia" (V2-5): one plan of the works for all the walls and the ceiling of a room, in a sheet over the list of surfaces. The server brings
 * every wall and the ceiling that follows it (or has no plan) to the same works, and says which surfaces it left alone: a plan of its own, or work that has started.
 */
export function RoomPlanSheet({ projectId, roomId, onClose, onSaved }: RoomPlanSheetProps) {
  const { t } = useI18n();
  const text = t.roomplan;
  const [items, setItems] = useState<PriceItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [substrate, setSubstrate] = useState<SubstrateValue>('GYPSUM_PLASTER');
  const [quality, setQuality] = useState<QualityLevelValue | ''>('S2');
  const [lists, setLists] = useState<Record<Target, string[]>>({ walls: [], ceiling: [] });
  const [picked, setPicked] = useState<Record<Target, string>>({ walls: '', ceiling: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<RoomWorkPlanResponse | null>(null);
  const [sources, setSources] = useState<SurfacePlanState[]>([]);
  const [source, setSource] = useState('');
  const [loadingSource, setLoadingSource] = useState(false);
  const [rooms, setRooms] = useState<{ id: string; name: string }[]>([]);
  const [otherRoom, setOtherRoom] = useState('');
  const [copying, setCopying] = useState(false);
  const [processFor, setProcessFor] = useState<Target | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useTelegramBackButton(true, report ? () => { onSaved(); onClose(); } : onClose);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (report) onSaved();
      onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, onSaved, report]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve()
      .then(() => Promise.all([fetchPriceItems(), fetchRoomWorkPlan(projectId, roomId)]))
      .then(([catalog, found]) => {
        if (cancelled) return;
        setItems(catalog.items);
        setSources(found.surfaces.filter((surface) => surface.state !== 'NONE')); // only a surface that has a plan can be copied from
        if (found.plan) {
          setSubstrate(found.plan.substrate);
          setQuality(found.plan.quality_target ?? '');
          setLists({ walls: found.plan.walls, ceiling: found.plan.ceiling });
        }
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    // the other rooms of the object, for "Skopiuj plan z innego pomieszczenia"; without them the choice is simply not shown
    void fetchRooms(projectId)
      .then((found) => {
        if (!cancelled) setRooms(found.items.filter((room) => room.id !== roomId).map((room) => ({ id: room.id, name: room.name })));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [projectId, roomId]);

  const byId = useMemo(() => new Map((items ?? []).map((item) => [item.id, item])), [items]);
  const grouped = useMemo(() => {
    const groups = new Map<PriceCategoryValue, PriceItem[]>();
    for (const item of items ?? []) groups.set(item.category, [...(groups.get(item.category) ?? []), item]);
    return [...groups.entries()];
  }, [items]);
  const nameOf = (id: string) => {
    const item = byId.get(id);
    return item ? resolveDisplayName(item, t as unknown as Record<string, unknown>) : '—';
  };

  const changeSubstrate = (value: SubstrateValue) => {
    setSubstrate(value);
    if (quality !== '' && !levelsFor(value).includes(quality)) setQuality(value === 'GYPSUM_BOARD' ? 'Q2' : 'S2');
  };
  const add = (target: Target) => {
    if (!picked[target]) return;
    setLists((current) => ({ ...current, [target]: [...current[target], picked[target]] }));
    setPicked((current) => ({ ...current, [target]: '' }));
  };
  const remove = (target: Target, index: number) => setLists((current) => ({ ...current, [target]: current[target].filter((_, at) => at !== index) }));
  const move = (target: Target, index: number, step: -1 | 1) =>
    setLists((current) => {
      const next = [...current[target]];
      const to = index + step;
      if (to < 0 || to >= next.length) return current;
      [next[index], next[to]] = [next[to], next[index]];
      return { ...current, [target]: next };
    });

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      setReport(await saveRoomWorkPlan(projectId, roomId, { substrate, quality_target: quality === '' ? null : quality, walls: lists.walls, ceiling: lists.ceiling }));
    } catch (failure) {
      const code = failure instanceof RoomPlanRequestError ? failure.code : null;
      setError((code ? (text as unknown as Record<string, string>)[`err_${code}`] : undefined) ?? text.save_failed);
    } finally {
      setBusy(false);
    }
  };

  // "Wczytaj ze ściany": the works, the substrate and the class of a surface go into the list of its kind (a wall -> the walls, the ceiling -> the ceiling)
  const loadFromSurface = async () => {
    const chosen = sources.find((surface) => surface.surface_id === source);
    if (!chosen) return;
    setLoadingSource(true);
    setError(null);
    try {
      const plan = await fetchSurfaceWorkPlan(projectId, roomId, chosen.surface_id);
      setSubstrate(plan.substrate);
      setQuality(plan.quality_target ?? '');
      const ids = plan.planned_works.map((work) => work.price_item_id);
      setLists((current) => (chosen.surface_type === 'CEILING' ? { ...current, ceiling: ids } : { ...current, walls: ids }));
    } catch {
      setError(text.load_surface_failed);
    } finally {
      setLoadingSource(false);
    }
  };

  // B1 "Skopiuj plan z innego pomieszczenia": its plan of the room; a room without one gives the plans of its first wall and its ceiling
  const copyFromRoom = async () => {
    const chosen = rooms.find((room) => room.id === otherRoom);
    if (!chosen) return;
    setCopying(true);
    setError(null);
    setNotice(null);
    try {
      const found = await fetchRoomWorkPlan(projectId, chosen.id);
      if (found.plan) {
        setSubstrate(found.plan.substrate);
        setQuality(found.plan.quality_target ?? '');
        setLists({ walls: found.plan.walls, ceiling: found.plan.ceiling });
      } else {
        const planned = found.surfaces.filter((surface) => surface.state !== 'NONE');
        const firstWall = planned.find((surface) => surface.surface_type === 'WALL');
        const ceiling = planned.find((surface) => surface.surface_type === 'CEILING');
        if (!firstWall && !ceiling) {
          setError(text.copy_room_none);
          return;
        }
        const [wallPlan, ceilingPlan] = await Promise.all([
          firstWall ? fetchSurfaceWorkPlan(projectId, chosen.id, firstWall.surface_id) : Promise.resolve(null),
          ceiling ? fetchSurfaceWorkPlan(projectId, chosen.id, ceiling.surface_id) : Promise.resolve(null),
        ]);
        const lead = wallPlan ?? ceilingPlan;
        if (lead) {
          setSubstrate(lead.substrate);
          setQuality(lead.quality_target ?? '');
        }
        setLists({
          walls: wallPlan ? wallPlan.planned_works.map((work) => work.price_item_id) : [],
          ceiling: ceilingPlan ? ceilingPlan.planned_works.map((work) => work.price_item_id) : [],
        });
      }
      setNotice(text.copy_room_done.replace('{name}', chosen.name));
    } catch {
      setError(text.copy_room_failed);
    } finally {
      setCopying(false);
    }
  };

  const pickProcess = (target: Target, ids: string[], mode: 'replace' | 'append') => {
    setLists((current) => ({ ...current, [target]: mode === 'replace' ? ids : [...current[target], ...ids] }));
    setProcessFor(null);
    setError(null);
    setNotice(text.process_inserted.replace('{n}', String(ids.length)));
  };

  const finish = () => {
    onSaved();
    onClose();
  };

  // the stored names ("Wall 1", "Ceiling") are language-neutral: they are shown the way the lists show them
  const labels = { wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling };
  const names = (outcome: string) =>
    (report?.results ?? []).filter((r) => r.outcome === outcome).map((r) => getSurfaceDisplayName({ name: r.name, surface_type: r.surface_type }, labels));
  const count = (...outcomes: string[]) => (report?.results ?? []).filter((r) => outcomes.includes(r.outcome)).length;

  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={text.title} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50">
      <div aria-label="room-plan-sheet" className="pe-card w-full max-w-lg rounded-t-2xl sm:rounded-2xl p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-xl space-y-3 max-h-[92vh] overflow-y-auto">
        <h4 className="font-semibold text-slate-900 break-words">{text.title}</h4>
        {report ? (
          <div aria-label="room-plan-report" className="space-y-2">
            <p className="text-sm font-semibold text-slate-900 break-words">{text.report_title}</p>
            {count('CREATED') > 0 && <p className="text-sm text-slate-700 break-words">{text.report_created.replace('{n}', String(count('CREATED')))}</p>}
            {count('UPDATED') > 0 && <p className="text-sm text-slate-700 break-words">{text.report_updated.replace('{n}', String(count('UPDATED')))}</p>}
            {count('SKIPPED_OWN') > 0 && <p className="text-sm text-amber-700 break-words">{text.report_skipped_own.replace('{names}', names('SKIPPED_OWN').join(', '))}</p>}
            {count('SKIPPED_STARTED') > 0 && <p className="text-sm text-amber-700 break-words">{text.report_skipped_started.replace('{names}', names('SKIPPED_STARTED').join(', '))}</p>}
            <button type="button" aria-label="room-plan-close" onClick={finish} className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-blue-600 text-white hover:bg-blue-700">
              <Ico>✅</Ico>{text.report_close}
            </button>
          </div>
        ) : (
          <>
            <p className="text-xs text-slate-600 break-words">{text.intro}</p>
            {!items && !loadFailed && <p className="text-sm text-slate-500 text-center py-4">{t.pricebook.loading}</p>}
            {loadFailed && <p role="alert" className="text-sm text-red-600 break-words">{text.load_failed}</p>}
            {items && (
              <>
                {rooms.length > 0 && (
                  <section aria-label="room-plan-copy-room" className="space-y-1.5">
                    <div className="flex items-center gap-1.5">
                      <select aria-label="room-plan-copy-room-pick" value={otherRoom} onChange={(event) => setOtherRoom(event.target.value)} className={`${inputClass} min-w-0 flex-1`}>
                        <option value="">{text.copy_room_pick}</option>
                        {rooms.map((room) => (
                          <option key={room.id} value={room.id}>{room.name}</option>
                        ))}
                      </select>
                      <button type="button" aria-label="room-plan-copy-room-button" disabled={!otherRoom || copying} onClick={() => void copyFromRoom()} className="shrink-0 min-h-11 px-3 text-sm font-semibold rounded-xl border border-slate-300 text-slate-800 hover:bg-slate-100 disabled:opacity-40 break-words">
                        <Ico>📋</Ico>{text.copy_room_button}
                      </button>
                    </div>
                    <p className="text-xs text-slate-500 break-words">{text.copy_room_hint}</p>
                  </section>
                )}
                {sources.length > 0 && (
                  <section aria-label="room-plan-load" className="space-y-1.5">
                    <div className="flex items-center gap-1.5">
                      <select aria-label="room-plan-load-pick" value={source} onChange={(event) => setSource(event.target.value)} className={`${inputClass} min-w-0 flex-1`}>
                        <option value="">{text.load_pick}</option>
                        {sources.map((surface) => (
                          <option key={surface.surface_id} value={surface.surface_id}>
                            {getSurfaceDisplayName({ name: surface.name, surface_type: surface.surface_type }, labels)}
                          </option>
                        ))}
                      </select>
                      <button type="button" aria-label="room-plan-load-button" disabled={!source || loadingSource} onClick={() => void loadFromSurface()} className="shrink-0 min-h-11 px-3 text-sm font-semibold rounded-xl border border-slate-300 text-slate-800 hover:bg-slate-100 disabled:opacity-40 break-words">
                        <Ico>📥</Ico>{text.load_button}
                      </button>
                    </div>
                    <p className="text-xs text-slate-500 break-words">{text.load_hint}</p>
                  </section>
                )}
                <div className="grid grid-cols-1 gap-2">
                  <div>
                    <label htmlFor="room-plan-substrate" className="block text-xs text-slate-500 mb-1">{text.substrate}</label>
                    <select id="room-plan-substrate" aria-label="room-plan-substrate" value={substrate} onChange={(event) => changeSubstrate(event.target.value as SubstrateValue)} className={inputClass}>
                      {SUBSTRATES.map((value) => (
                        <option key={value} value={value}>{(t.inspections as unknown as Record<string, string>)[substrateKey[value]]}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="room-plan-quality" className="block text-xs text-slate-500 mb-1">{text.quality}</label>
                    <select id="room-plan-quality" aria-label="room-plan-quality" value={quality} onChange={(event) => setQuality(event.target.value as QualityLevelValue | '')} className={inputClass}>
                      <option value="">{t.inspections.quality_optional}</option>
                      {levelsFor(substrate).map((level) => (
                        <option key={level} value={level}>{t.pricebook.quality[level]}</option>
                      ))}
                    </select>
                  </div>
                </div>
                {(['walls', 'ceiling'] as const).map((target) => (
                  <section key={target} aria-label={`room-plan-${target}`} className="space-y-2">
                    <h5 className="text-sm font-semibold text-slate-900">{target === 'walls' ? text.walls : text.ceiling}</h5>
                    {lists[target].length === 0 && <p className="text-xs text-slate-500">{text.no_works}</p>}
                    {lists[target].map((id, index) => (
                      <div key={`${id}-${index}`} aria-label={`room-plan-${target}-work-${index}`} className="flex items-center gap-1.5">
                        <span className="min-w-0 flex-1 text-sm text-slate-900 break-words">{index + 1}. {nameOf(id)}</span>
                        <button type="button" aria-label={`room-plan-${target}-up-${index}`} title={text.move_up} disabled={index === 0} onClick={() => move(target, index, -1)} className={iconButton}>↑</button>
                        <button type="button" aria-label={`room-plan-${target}-down-${index}`} title={text.move_down} disabled={index === lists[target].length - 1} onClick={() => move(target, index, 1)} className={iconButton}>↓</button>
                        <button type="button" aria-label={`room-plan-${target}-remove-${index}`} title={text.remove_work} onClick={() => remove(target, index)} className={iconButton}>✕</button>
                      </div>
                    ))}
                    <div className="flex items-center gap-1.5">
                      <select aria-label={`room-plan-${target}-pick`} value={picked[target]} onChange={(event) => setPicked((current) => ({ ...current, [target]: event.target.value }))} className={`${inputClass} min-w-0 flex-1`}>
                        <option value="">{text.pick_work}</option>
                        {grouped.map(([category, rows]) => (
                          <optgroup key={category} label={t.pricebook.categories[category]}>
                            {rows.map((item) => (
                              <option key={item.id} value={item.id}>{resolveDisplayName(item, t as unknown as Record<string, unknown>)}</option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                      <button type="button" aria-label={`room-plan-${target}-add`} disabled={!picked[target]} onClick={() => add(target)} className="shrink-0 min-h-11 px-3 text-sm font-semibold rounded-xl border border-slate-300 text-slate-800 hover:bg-slate-100 disabled:opacity-40">
                        <Ico>➕</Ico>{text.add_work}
                      </button>
                    </div>
                    {processFor === target ? (
                      <RoomPlanProcessPicker
                        target={target}
                        substrate={substrate}
                        quality={quality}
                        hasWorks={lists[target].length > 0}
                        nameOf={nameOf}
                        onPick={(ids, mode) => pickProcess(target, ids, mode)}
                        onClose={() => setProcessFor(null)}
                      />
                    ) : (
                      <button type="button" aria-label={`room-plan-${target}-process-open`} onClick={() => { setProcessFor(target); setNotice(null); }} className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-blue-300 text-blue-700 hover:bg-blue-50 break-words">
                        <Ico>📂</Ico>{text.process_open}
                      </button>
                    )}
                  </section>
                ))}
              </>
            )}
            {notice && !error && <p role="status" aria-label="room-plan-notice" className="text-sm text-emerald-700 break-words">{notice}</p>}
            {error && <p role="alert" className="text-sm text-red-600 font-medium break-words">{error}</p>}
            <div className="flex gap-2 justify-end">
              <button type="button" aria-label="room-plan-cancel" onClick={onClose} className="min-h-11 px-3 py-1 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50">
                <Ico>✖️</Ico>{t.common.cancel}
              </button>
              <button type="button" aria-label="room-plan-save" disabled={busy || !items} onClick={() => void save()} className="min-h-11 px-3 py-1 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50">
                <Ico>💾</Ico>{busy ? t.common.saving : text.save}
              </button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
