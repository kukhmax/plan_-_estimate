import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  archiveAdjacentWork,
  createAdjacentWork,
  fetchAdjacentWorks,
  restoreAdjacentWork,
  updateAdjacentWork,
} from '../api/adjacentWorks';
import { ApiError } from '../api/http';
import { fetchRooms } from '../api/rooms';
import { useI18n } from '../hooks/useI18n';
import { ADJACENT_WORK_ORDERS, AdjacentWork, AdjacentWorkOrder } from '../types/adjacentWork';
import type { RoomType } from '../types/room';

interface ProjectAdjacentWorksProps {
  projectId: string;
}

interface FormState {
  work_name: string;
  performer: string;
  wholeObject: boolean;
  room_ids: string[];
  period_from: string;
  period_to: string;
  order_relation: AdjacentWorkOrder;
  order_note: string;
  responsibility_note: string;
  coordination_note: string;
}

const EMPTY_FORM: FormState = {
  work_name: '', performer: '', wholeObject: true, room_ids: [], period_from: '', period_to: '',
  order_relation: 'BEFORE_OURS', order_note: '', responsibility_note: '', coordination_note: '',
};

function formFrom(work: AdjacentWork): FormState {
  return {
    work_name: work.work_name,
    performer: work.performer ?? '',
    wholeObject: work.room_ids === null,
    room_ids: work.room_ids ?? [],
    period_from: work.period_from ?? '',
    period_to: work.period_to ?? '',
    order_relation: work.order_relation,
    order_note: work.order_note ?? '',
    responsibility_note: work.responsibility_note ?? '',
    coordination_note: work.coordination_note ?? '',
  };
}

const FIELD = 'w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-base bg-white text-slate-900';

/**
 * Stage 16D.1 — works of other contractors on the object (electrics, plumbing, tiles, the developer's crew): who does what, in
 * which rooms, when, and how it is ordered against our own works. The production plan and the contract refer to this register.
 * An entry is archived, never deleted.
 */
export function ProjectAdjacentWorks({ projectId }: ProjectAdjacentWorksProps) {
  const { t } = useI18n();
  const text = t.adjacentWorks;
  const [items, setItems] = useState<AdjacentWork[]>([]);
  const [rooms, setRooms] = useState<RoomType[]>([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [editing, setEditing] = useState<AdjacentWork | 'new' | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const [list, roomList] = await Promise.all([fetchAdjacentWorks(projectId, includeArchived), fetchRooms(projectId)]);
      if (!alive.current) return;
      setItems(list.items);
      setRooms(roomList.items);
    } catch {
      if (alive.current) setLoadFailed(true);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [projectId, includeArchived]);

  useEffect(() => {
    void load();
  }, [load]);

  const roomName = (id: string) => rooms.find((room) => room.id === id)?.name ?? text.room_unknown;

  const openForm = (target: AdjacentWork | 'new') => {
    setEditing(target);
    setForm(target === 'new' ? EMPTY_FORM : formFrom(target));
    setFormError(null);
  };
  const closeForm = () => {
    setEditing(null);
    setFormError(null);
  };
  const change = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => ({ ...current, [key]: value }));
  const toggleRoom = (id: string) =>
    setForm((current) => ({
      ...current,
      room_ids: current.room_ids.includes(id) ? current.room_ids.filter((x) => x !== id) : [...current.room_ids, id],
    }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (saving || editing === null) return;
    const name = form.work_name.trim();
    if (name === '') return setFormError(text.validation_name);
    if (!form.wholeObject && form.room_ids.length === 0) return setFormError(text.validation_rooms);
    if (form.period_from && form.period_to && form.period_to < form.period_from) return setFormError(text.validation_period);
    setSaving(true);
    setFormError(null);
    const rooms_ = form.wholeObject ? null : form.room_ids;
    try {
      if (editing === 'new') {
        await createAdjacentWork(projectId, {
          work_name: name,
          performer: form.performer.trim() || undefined,
          room_ids: rooms_ ?? undefined,
          period_from: form.period_from || undefined,
          period_to: form.period_to || undefined,
          order_relation: form.order_relation,
          order_note: form.order_note.trim() || undefined,
          responsibility_note: form.responsibility_note.trim() || undefined,
          coordination_note: form.coordination_note.trim() || undefined,
        });
      } else {
        // an emptied optional field is removed (null)
        await updateAdjacentWork(projectId, editing.id, {
          work_name: name,
          performer: form.performer.trim() || null,
          room_ids: rooms_,
          period_from: form.period_from || null,
          period_to: form.period_to || null,
          order_relation: form.order_relation,
          order_note: form.order_note.trim() || null,
          responsibility_note: form.responsibility_note.trim() || null,
          coordination_note: form.coordination_note.trim() || null,
        });
      }
      if (!alive.current) return;
      closeForm();
      await load();
    } catch (err) {
      if (!alive.current) return;
      const code = err instanceof ApiError ? err.code : undefined;
      setFormError(code === 'ADJACENT_WORK_ROOM_INVALID' ? text.room_invalid : code === 'ADJACENT_WORK_PERIOD_INVALID' ? text.validation_period : text.save_failed);
    } finally {
      if (alive.current) setSaving(false);
    }
  };

  const toggleArchive = async (work: AdjacentWork) => {
    if (busyId) return;
    setBusyId(work.id);
    try {
      if (work.is_archived) await restoreAdjacentWork(projectId, work.id);
      else await archiveAdjacentWork(projectId, work.id);
      if (alive.current) await load();
    } catch {
      if (alive.current) setLoadFailed(true);
    } finally {
      if (alive.current) setBusyId(null);
    }
  };

  const period = (work: AdjacentWork): string | null => {
    if (work.period_from && work.period_to) return `${work.period_from} – ${work.period_to}`;
    if (work.period_from) return text.period_from_only.replace('{date}', work.period_from);
    if (work.period_to) return text.period_to_only.replace('{date}', work.period_to);
    return null;
  };

  return (
    <article aria-label="project-adjacent-works" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{text.title}</h3>
        {editing === null && (
          <button
            type="button"
            aria-label="add-adjacent-work"
            onClick={() => openForm('new')}
            className="min-h-11 px-4 shrink-0 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 transition"
          >
            {text.add}
          </button>
        )}
      </div>
      <p className="text-xs text-slate-600 break-words">{text.intro}</p>

      {editing !== null && (
        <form aria-label="adjacent-work-form" onSubmit={submit} className="space-y-2 border border-slate-200 rounded-xl p-3 bg-slate-50">
          <h4 className="text-sm font-semibold text-slate-900 break-words">{editing === 'new' ? text.form_title_add : text.form_title_edit}</h4>
          <input aria-label="adjacent-work-name" placeholder={text.work_name} value={form.work_name} onChange={(e) => change('work_name', e.target.value)} className={FIELD} />
          <input aria-label="adjacent-work-performer" placeholder={text.performer} value={form.performer} onChange={(e) => change('performer', e.target.value)} className={FIELD} />
          <fieldset className="space-y-1">
            <legend className="text-xs font-medium text-slate-600">{text.rooms}</legend>
            <label className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
              <input type="checkbox" aria-label="adjacent-work-whole-object" className="h-5 w-5 shrink-0" checked={form.wholeObject} onChange={(e) => change('wholeObject', e.target.checked)} />
              <span className="min-w-0 break-words">{text.whole_object}</span>
            </label>
            {!form.wholeObject &&
              rooms.map((room) => (
                <label key={room.id} className="flex items-center gap-3 min-h-11 text-sm text-slate-900">
                  <input type="checkbox" aria-label={`adjacent-work-room-${room.id}`} className="h-5 w-5 shrink-0" checked={form.room_ids.includes(room.id)} onChange={() => toggleRoom(room.id)} />
                  <span className="min-w-0 break-words">{room.name}</span>
                </label>
              ))}
          </fieldset>
          <label className="block text-xs font-medium text-slate-600">
            {text.period_from}
            <input aria-label="adjacent-work-from" type="date" value={form.period_from} onChange={(e) => change('period_from', e.target.value)} className={`${FIELD} mt-1`} />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            {text.period_to}
            <input aria-label="adjacent-work-to" type="date" value={form.period_to} onChange={(e) => change('period_to', e.target.value)} className={`${FIELD} mt-1`} />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            {text.order_relation}
            <select aria-label="adjacent-work-order" value={form.order_relation} onChange={(e) => change('order_relation', e.target.value as AdjacentWorkOrder)} className={`${FIELD} mt-1`}>
              {ADJACENT_WORK_ORDERS.map((order) => (
                <option key={order} value={order}>
                  {text[`order_${order}`]}
                </option>
              ))}
            </select>
          </label>
          <textarea aria-label="adjacent-work-order-note" placeholder={text.order_note} value={form.order_note} rows={2} onChange={(e) => change('order_note', e.target.value)} className={FIELD} />
          <textarea aria-label="adjacent-work-responsibility" placeholder={text.responsibility_note} value={form.responsibility_note} rows={2} onChange={(e) => change('responsibility_note', e.target.value)} className={FIELD} />
          <textarea aria-label="adjacent-work-coordination" placeholder={text.coordination_note} value={form.coordination_note} rows={2} onChange={(e) => change('coordination_note', e.target.value)} className={FIELD} />
          {formError && (
            <p role="alert" aria-label="adjacent-work-error" className="text-sm text-red-700 break-words">
              {formError}
            </p>
          )}
          <button type="submit" disabled={saving} className="w-full min-h-11 px-3 text-sm font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-60 transition">
            {text.save}
          </button>
          <button type="button" onClick={closeForm} disabled={saving} className="w-full min-h-11 px-3 text-sm font-semibold text-slate-800 bg-white border border-slate-300 rounded-xl hover:bg-slate-100 disabled:opacity-60 transition">
            {text.cancel}
          </button>
        </form>
      )}

      {loading && items.length === 0 && <p role="status" className="text-sm text-slate-600">{text.loading}</p>}
      {loadFailed && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-red-700 break-words">{text.load_failed}</p>
          <button type="button" onClick={() => void load()} className="w-full min-h-11 text-sm font-semibold text-slate-800 bg-slate-100 border border-slate-200 rounded-xl">
            {text.retry}
          </button>
        </div>
      )}
      {!loading && !loadFailed && items.length === 0 && <p className="text-sm text-slate-600 break-words">{text.empty}</p>}

      {items.length > 0 && (
        <ul className="space-y-2">
          {items.map((work) => (
            <li key={work.id} aria-label={`adjacent-work-${work.id}`} className="border border-slate-200 rounded-xl p-3 space-y-1">
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 break-words text-sm font-semibold text-slate-900">{work.work_name}</span>
                {work.is_archived && <span className="shrink-0 text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-800 font-medium">{text.archived_badge}</span>}
              </div>
              {work.performer && <p className="text-xs text-slate-700 break-words">{work.performer}</p>}
              <p className="text-xs text-slate-700 break-words">{text[`order_${work.order_relation}`]}</p>
              <p className="text-xs text-slate-600 break-words">
                {work.room_ids === null ? text.whole_object : work.room_ids.map(roomName).join(', ')}
              </p>
              {period(work) && <p className="text-xs text-slate-600 break-words">{period(work)}</p>}
              {work.order_note && <p className="text-xs text-slate-600 break-words">{work.order_note}</p>}
              {work.responsibility_note && <p className="text-xs text-slate-600 break-words">{work.responsibility_note}</p>}
              {work.coordination_note && <p className="text-xs text-slate-600 break-words">{work.coordination_note}</p>}
              <div className="flex flex-wrap gap-2 pt-1">
                {!work.is_archived && (
                  <button type="button" aria-label={`edit-adjacent-work-${work.id}`} onClick={() => openForm(work)} className="min-h-11 px-4 text-sm font-semibold text-slate-800 bg-slate-100 border border-slate-200 rounded-xl hover:bg-slate-200 transition">
                    {text.edit}
                  </button>
                )}
                <button
                  type="button"
                  aria-label={`${work.is_archived ? 'restore' : 'archive'}-adjacent-work-${work.id}`}
                  disabled={busyId === work.id}
                  onClick={() => void toggleArchive(work)}
                  className="min-h-11 px-4 text-sm font-semibold text-slate-800 bg-white border border-slate-300 rounded-xl hover:bg-slate-100 disabled:opacity-60 transition"
                >
                  {work.is_archived ? text.restore : text.archive}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <label className="flex items-center gap-3 min-h-11 text-sm text-slate-700">
        <input type="checkbox" aria-label="show-archived-adjacent-works" className="h-5 w-5 shrink-0" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
        <span className="min-w-0 break-words">{text.show_archived}</span>
      </label>
    </article>
  );
}
