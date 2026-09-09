import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  archiveRoom,
  createRoom,
  fetchRooms,
  restoreRoom,
  updateRoom,
} from '../api/rooms';
import { useI18n } from '../hooks/useI18n';
import { RoomCreatePayload, RoomType } from '../types/room';

interface RoomListProps {
  projectId: string;
  onOpenRoom: (room: RoomType) => void;
}

interface RoomFormState {
  name: string;
  description: string;
}

const EMPTY_FORM: RoomFormState = { name: '', description: '' };

export function RoomList({ projectId, onOpenRoom }: RoomListProps) {
  const { t } = useI18n();
  const [rooms, setRooms] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [form, setForm] = useState<RoomFormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRooms(projectId, includeArchived);
      setRooms(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.rooms.error);
    } finally {
      setLoading(false);
    }
  }, [includeArchived, projectId, t.rooms.error]);

  useEffect(() => {
    void load();
  }, [load]);

  const closeForm = () => {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const startCreate = () => {
    setSuccess(null);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setShowForm(true);
  };

  const startEdit = (room: RoomType) => {
    setSuccess(null);
    setEditingId(room.id);
    setForm({ name: room.name, description: room.description ?? '' });
    setFormError(null);
    setShowForm(true);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    const payload: RoomCreatePayload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
    };

    try {
      if (editingId) {
        await updateRoom(projectId, editingId, payload);
        setSuccess(t.rooms.updated);
      } else {
        await createRoom(projectId, payload);
        setSuccess(t.rooms.created);
      }
      closeForm();
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t.rooms.error);
    } finally {
      setSaving(false);
    }
  };

  const changeArchiveState = async (room: RoomType) => {
    setError(null);
    setSuccess(null);
    try {
      if (room.is_archived) {
        await restoreRoom(projectId, room.id);
        setSuccess(t.rooms.restored);
      } else {
        await archiveRoom(projectId, room.id);
        setSuccess(t.rooms.archived);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.rooms.error);
    }
  };

  return (
    <section aria-label="rooms-section" className="w-full mt-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="text-lg font-bold text-slate-900">{t.rooms.title}</h3>
        <button
          type="button"
          aria-label="add-room"
          onClick={startCreate}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
        >
          {t.rooms.add}
        </button>
      </div>

      <label className="flex items-center gap-1.5 text-sm text-slate-600 mb-3 cursor-pointer">
        <input
          aria-label="show-archived-rooms"
          type="checkbox"
          checked={includeArchived}
          onChange={(event) => setIncludeArchived(event.target.checked)}
        />
        {t.common.show_archived}
      </label>

      {showForm && (
        <form
          aria-label="room-form"
          onSubmit={handleSubmit}
          className="bg-white border border-slate-200 rounded-2xl p-4 mb-4 shadow-sm space-y-3"
        >
          <h4 className="font-semibold text-slate-900">
            {editingId ? t.rooms.edit : t.rooms.add}
          </h4>
          <input
            aria-label="room-name"
            required
            maxLength={255}
            placeholder={t.rooms.name}
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <textarea
            aria-label="room-description"
            maxLength={4096}
            placeholder={t.rooms.description}
            value={form.description}
            onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-20"
          />
          {formError && <p role="alert" className="text-sm text-red-600 font-medium">{formError}</p>}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={closeForm}
              className="px-3 py-1.5 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
            >
              {t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              {saving ? t.common.saving : t.common.save}
            </button>
          </div>
        </form>
      )}

      {success && <p role="status" className="text-sm text-emerald-700 mb-3">{success}</p>}
      {loading && <p className="text-sm text-slate-500 text-center py-4">{t.rooms.loading}</p>}
      {!loading && error && <p role="alert" className="text-sm text-red-600 text-center py-4">{error}</p>}
      {!loading && !error && rooms.length === 0 && (
        <p aria-label="no-rooms" className="text-sm text-slate-400 text-center py-6">
          {t.rooms.empty}
        </p>
      )}
      {!loading && !error && rooms.length > 0 && (
        <ul aria-label="rooms-list" className="space-y-2">
          {rooms.map((room) => (
            <li
              key={room.id}
              aria-label={`room-item-${room.id}`}
              className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-slate-900 text-sm">{room.name}</span>
                    {room.is_archived && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                        {t.common.archived_badge}
                      </span>
                    )}
                  </div>
                  {room.description && <p className="text-xs text-slate-500 mt-1">{room.description}</p>}
                </div>
                <div className="flex gap-1.5 flex-wrap justify-end">
                  <button
                    type="button"
                    aria-label={`open-room-${room.id}`}
                    onClick={() => onOpenRoom(room)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
                  >
                    {t.common.open}
                  </button>
                  <button
                    type="button"
                    aria-label={`edit-room-${room.id}`}
                    onClick={() => startEdit(room)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                  >
                    {t.common.edit}
                  </button>
                  <button
                    type="button"
                    aria-label={`${room.is_archived ? 'restore' : 'archive'}-room-${room.id}`}
                    onClick={() => void changeArchiveState(room)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                  >
                    {room.is_archived ? t.common.restore : t.common.archive}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
