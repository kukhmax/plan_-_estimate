import { FormEvent, useCallback, useEffect, useState } from 'react';
import { fetchClients } from '../api/clients';
import {
  archiveProject,
  createProject,
  fetchProjects,
  restoreProject,
  updateProject,
} from '../api/projects';
import { fetchRoom, updateRoom } from '../api/rooms';
import { useI18n } from '../hooks/useI18n';
import { resolveRoomMeasurementMode } from '../hooks/roomMeasurementMode';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { ClientType } from '../types/client';
import {
  ProjectCreatePayload,
  ProjectStatus,
  ProjectType,
} from '../types/project';
import { RoomType, RoomUpdatePayload } from '../types/room';
import { InspectionTarget } from '../types/inspection';
import { formatMetric } from '../utils/format';
import { AreaSegmentList } from './AreaSegmentList';
import { InspectionFlow } from './InspectionFlow';
import { InspectionList } from './InspectionList';
import { RoomList } from './RoomList';
import { SurfaceList } from './SurfaceList';

interface ProjectFormState {
  name: string;
  address: string;
  city: string;
  postal_code: string;
  description: string;
  status: ProjectStatus;
  client_id: string;
}

const EMPTY_FORM: ProjectFormState = {
  name: '',
  address: '',
  city: '',
  postal_code: '',
  description: '',
  status: 'PLANNING',
  client_id: '',
};

interface RoomEditFormState {
  name: string;
  description: string;
  length: string;
  width: string;
  height: string;
}

const EMPTY_ROOM_FORM: RoomEditFormState = {
  name: '',
  description: '',
  length: '',
  width: '',
  height: '',
};

function clientName(client: ClientType): string {
  if (client.client_type === 'COMPANY') return client.company_name ?? '—';
  return [client.first_name, client.last_name].filter(Boolean).join(' ') || '—';
}

function formFromProject(project: ProjectType): ProjectFormState {
  return {
    name: project.name,
    address: project.address,
    city: project.city,
    postal_code: project.postal_code,
    description: project.description ?? '',
    status: project.status,
    client_id: project.client_id ?? '',
  };
}

interface ProjectWorkspaceProps {
  resetSignal?: number;
}

export function ProjectWorkspace({ resetSignal }: ProjectWorkspaceProps) {
  const { t } = useI18n();
  const [projects, setProjects] = useState<ProjectType[]>([]);
  const [clients, setClients] = useState<ClientType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [selectedProject, setSelectedProject] = useState<ProjectType | null>(null);
  const [selectedRoom, setSelectedRoom] = useState<RoomType | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ProjectFormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [showRoomForm, setShowRoomForm] = useState(false);
  const [roomForm, setRoomForm] = useState<RoomEditFormState>(EMPTY_ROOM_FORM);
  const [roomFormError, setRoomFormError] = useState<string | null>(null);
  const [savingRoom, setSavingRoom] = useState(false);

  const [inspectionTarget, setInspectionTarget] = useState<InspectionTarget | null>(null);
  const [activeInspection, setActiveInspection] = useState<{
    target: InspectionTarget;
    inspectionId: string | null;
  } | null>(null);
  const [listVersion, setListVersion] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [projectData, clientData] = await Promise.all([
        fetchProjects(includeArchived),
        fetchClients({ include_archived: true }),
      ]);
      setProjects(projectData.items);
      setClients(clientData.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.projects.error);
    } finally {
      setLoading(false);
    }
  }, [includeArchived, t.projects.error]);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshSelectedRoom = useCallback(async () => {
    if (!selectedProject || !selectedRoom) return;
    try {
      const refreshed = await fetchRoom(selectedProject.id, selectedRoom.id);
      setSelectedRoom(refreshed);
    } catch {
      // keep current state if refresh fails
    }
  }, [selectedProject, selectedRoom]);

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

  const startEdit = (project: ProjectType) => {
    setSuccess(null);
    setEditingId(project.id);
    setForm(formFromProject(project));
    setFormError(null);
    setShowForm(true);
  };

  const startEditRoom = (room: RoomType) => {
    setRoomForm({
      name: room.name,
      description: room.description ?? '',
      length: room.length !== null && room.length !== undefined ? String(room.length) : '',
      width: room.width !== null && room.width !== undefined ? String(room.width) : '',
      height: room.height !== null && room.height !== undefined ? String(room.height) : '',
    });
    setRoomFormError(null);
    setShowRoomForm(true);
  };

  const handleRoomSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedProject || !selectedRoom) return;
    setSavingRoom(true);
    setRoomFormError(null);

    const lengthVal = roomForm.length.trim() ? parseFloat(roomForm.length.trim()) : null;
    const widthVal = roomForm.width.trim() ? parseFloat(roomForm.width.trim()) : null;
    const heightVal = roomForm.height.trim() ? parseFloat(roomForm.height.trim()) : null;

    if (lengthVal !== null && (Number.isNaN(lengthVal) || lengthVal <= 0)) {
      setRoomFormError(t.rooms.error);
      setSavingRoom(false);
      return;
    }
    if (widthVal !== null && (Number.isNaN(widthVal) || widthVal <= 0)) {
      setRoomFormError(t.rooms.error);
      setSavingRoom(false);
      return;
    }
    if (heightVal !== null && (Number.isNaN(heightVal) || heightVal <= 0)) {
      setRoomFormError(t.rooms.error);
      setSavingRoom(false);
      return;
    }

    const payload: RoomUpdatePayload = {
      name: roomForm.name.trim(),
      description: roomForm.description.trim() || null,
      length: lengthVal,
      width: widthVal,
      height: heightVal,
    };

    try {
      const updated = await updateRoom(selectedProject.id, selectedRoom.id, payload);
      setSelectedRoom(updated);
      setShowRoomForm(false);
      setSuccess(t.rooms.updated);
    } catch (err) {
      setRoomFormError(err instanceof Error ? err.message : t.rooms.error);
    } finally {
      setSavingRoom(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    const payload: ProjectCreatePayload = {
      name: form.name.trim(),
      address: form.address.trim(),
      city: form.city.trim(),
      postal_code: form.postal_code.trim(),
      description: form.description.trim() || null,
      status: form.status,
      client_id: form.client_id || null,
    };

    try {
      if (editingId) {
        const updated = await updateProject(editingId, payload);
        if (selectedProject?.id === updated.id) setSelectedProject(updated);
        setSuccess(t.projects.updated);
      } else {
        const created = await createProject(payload);
        setSelectedProject(created);
        setSelectedRoom(null);
        setSuccess(t.projects.created);
      }
      closeForm();
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t.projects.error);
    } finally {
      setSaving(false);
    }
  };

  const changeArchiveState = async (project: ProjectType) => {
    setError(null);
    setSuccess(null);
    try {
      const updated = project.is_archived
        ? await restoreProject(project.id)
        : await archiveProject(project.id);
      if (selectedProject?.id === updated.id) setSelectedProject(updated);
      setSuccess(project.is_archived ? t.projects.restored : t.projects.archived);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.projects.error);
    }
  };

  const statusLabel = (status: ProjectStatus) => {
    const labels: Record<ProjectStatus, string> = {
      PLANNING: t.projects.planning,
      IN_PROGRESS: t.projects.in_progress,
      COMPLETED: t.projects.completed,
    };
    return labels[status];
  };

  const assignedClientName = (project: ProjectType) => {
    if (!project.client_id) return t.projects.no_client;
    const client = clients.find((item) => item.id === project.client_id);
    return client ? clientName(client) : t.projects.client_unavailable;
  };

  const closeInspections = () => {
    setInspectionTarget(null);
    setActiveInspection(null);
  };

  const inspectionTargetKey = (target: InspectionTarget): string => {
    if (target.kind === 'surface') return `surface-${target.surfaceId}`;
    if (target.kind === 'plane') return `plane-${target.plane}`;
    return 'room';
  };

  const openInspectionList = (target: InspectionTarget) => {
    setActiveInspection(null);
    setInspectionTarget(target);
  };

  const openInspection = (target: InspectionTarget, inspectionId: string | null) => {
    setActiveInspection({ target, inspectionId });
  };

  const closeInspectionFlow = () => {
    setActiveInspection(null);
    setListVersion((version) => version + 1);
  };

  const openProject = (project: ProjectType) => {
    closeForm();
    setShowRoomForm(false);
    closeInspections();
    setSelectedProject(project);
    setSelectedRoom(null);
    setSuccess(null);
  };

  const openRoom = async (room: RoomType) => {
    closeForm();
    setShowRoomForm(false);
    closeInspections();
    setSelectedRoom(room);
    setSuccess(null);
    if (selectedProject) {
      try {
        const fullRoom = await fetchRoom(selectedProject.id, room.id);
        setSelectedRoom(fullRoom);
      } catch {
        // use room from list
      }
    }
  };

  const backToProjects = () => {
    closeForm();
    setShowRoomForm(false);
    closeInspections();
    setSelectedProject(null);
    setSelectedRoom(null);
    setSuccess(null);
  };

  const isBackButtonVisible = selectedProject !== null;

  const roomMeasurementMode =
    selectedRoom ? resolveRoomMeasurementMode(selectedRoom.id, selectedRoom) : 'RECTANGLE';

  // A RECTANGLE room is measured as soon as L × W × H are known; wall generation is not
  // required. The measurements summary must not depend on the optional calculations payload.
  const roomHasDraftDimensions =
    selectedRoom?.length !== null && selectedRoom?.length !== undefined &&
    selectedRoom?.width !== null && selectedRoom?.width !== undefined &&
    selectedRoom?.height !== null && selectedRoom?.height !== undefined;

  useEffect(() => {
    closeForm();
    setShowRoomForm(false);
    closeInspections();
    setSelectedProject(null);
    setSelectedRoom(null);
    setSuccess(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetSignal]);

  useTelegramBackButton(isBackButtonVisible, () => {
    if (showRoomForm) {
      setShowRoomForm(false);
    } else if (activeInspection) {
      setActiveInspection(null);
      setListVersion((version) => version + 1);
    } else if (inspectionTarget) {
      setInspectionTarget(null);
    } else if (selectedRoom) {
      setSelectedRoom(null);
    } else if (selectedProject) {
      backToProjects();
    }
  });

  return (
    <section aria-label="projects-workspace" className="w-full mt-4">
      {selectedProject && (
        <nav aria-label="hierarchy-navigation" className="flex items-center gap-1.5 flex-wrap text-xs text-slate-500 mb-3">
          <button
            type="button"
            aria-label="back-to-projects"
            onClick={backToProjects}
            className="font-semibold text-blue-700 hover:underline"
          >
            {t.projects.title}
          </button>
          <span>/</span>
          <span className="font-medium text-slate-700">{selectedProject.name}</span>
          <span>/</span>
          {selectedRoom ? (
            <>
              <button
                type="button"
                aria-label="back-to-rooms"
                onClick={() => {
                  setShowRoomForm(false);
                  closeInspections();
                  setSelectedRoom(null);
                }}
                className="font-semibold text-blue-700 hover:underline"
              >
                {t.rooms.title}
              </button>
              <span>/</span>
              <span className="font-medium text-slate-700">{selectedRoom.name}</span>
              <span>/</span>
              <span>{t.surfaces.title}</span>
            </>
          ) : (
            <span>{t.rooms.title}</span>
          )}
        </nav>
      )}

      {!selectedRoom && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h2 className="text-lg font-bold text-slate-900">
            {selectedProject ? selectedProject.name : t.projects.title}
          </h2>
          <button
            type="button"
            aria-label={selectedProject ? 'edit-project-detail' : 'add-project'}
            onClick={() => selectedProject ? startEdit(selectedProject) : startCreate()}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
          >
            {selectedProject ? t.common.edit : t.projects.add}
          </button>
        </div>
      )}

      {!selectedProject && (
        <label className="flex items-center gap-1.5 text-sm text-slate-600 mb-3 cursor-pointer">
          <input
            aria-label="show-archived-projects"
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          {t.common.show_archived}
        </label>
      )}

      {showForm && (
        <form
          aria-label="project-form"
          onSubmit={handleSubmit}
          className="bg-white border border-slate-200 rounded-2xl p-4 mb-4 shadow-sm space-y-3"
        >
          <h3 className="font-semibold text-slate-900">
            {editingId ? t.projects.edit : t.projects.add}
          </h3>
          <input
            aria-label="project-name"
            required
            maxLength={255}
            placeholder={t.projects.name}
            value={form.name}
            onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            aria-label="project-address"
            required
            maxLength={512}
            placeholder={t.projects.address}
            value={form.address}
            onChange={(event) => setForm((current) => ({ ...current, address: event.target.value }))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <input
              aria-label="project-city"
              required
              maxLength={255}
              placeholder={t.projects.city}
              value={form.city}
              onChange={(event) => setForm((current) => ({ ...current, city: event.target.value }))}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
            <input
              aria-label="project-postal-code"
              required
              maxLength={20}
              placeholder={t.projects.postal_code}
              value={form.postal_code}
              onChange={(event) => setForm((current) => ({ ...current, postal_code: event.target.value }))}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <select
            aria-label="project-status"
            value={form.status}
            onChange={(event) => setForm((current) => ({
              ...current,
              status: event.target.value as ProjectStatus,
            }))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            {(['PLANNING', 'IN_PROGRESS', 'COMPLETED'] as const).map((value) => (
              <option key={value} value={value}>{statusLabel(value)}</option>
            ))}
          </select>
          <select
            aria-label="project-client"
            value={form.client_id}
            onChange={(event) => setForm((current) => ({ ...current, client_id: event.target.value }))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            <option value="">{t.projects.no_client}</option>
            {clients.map((client) => (
              <option key={client.id} value={client.id}>{clientName(client)}</option>
            ))}
          </select>
          <textarea
            aria-label="project-description"
            maxLength={4096}
            placeholder={t.projects.description}
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
      {selectedProject && error && <p role="alert" className="text-sm text-red-600 mb-3">{error}</p>}

      {selectedProject && !selectedRoom && (
        <>
          <article aria-label="project-detail" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <dl className="space-y-1 text-sm min-w-0">
                <div><dt className="inline text-slate-500">{t.projects.address}: </dt><dd className="inline font-medium">{selectedProject.address}, {selectedProject.postal_code} {selectedProject.city}</dd></div>
                <div><dt className="inline text-slate-500">{t.projects.status}: </dt><dd className="inline font-medium">{statusLabel(selectedProject.status)}</dd></div>
                <div><dt className="inline text-slate-500">{t.projects.client}: </dt><dd className="inline font-medium">{assignedClientName(selectedProject)}</dd></div>
              </dl>
              <div className="flex items-center gap-2 flex-wrap justify-end">
                {selectedProject.is_archived && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                    {t.common.archived_badge}
                  </span>
                )}
                <button
                  type="button"
                  aria-label={`${selectedProject.is_archived ? 'restore' : 'archive'}-project-detail`}
                  onClick={() => void changeArchiveState(selectedProject)}
                  className="text-xs px-2.5 py-1 rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                >
                  {selectedProject.is_archived ? t.common.restore : t.common.archive}
                </button>
              </div>
            </div>
            {selectedProject.description && <p className="text-sm text-slate-600 mt-3">{selectedProject.description}</p>}
          </article>
          <RoomList
            projectId={selectedProject.id}
            onOpenRoom={openRoom}
            onRoomChanged={load}
          />
        </>
      )}

      {selectedProject && selectedRoom && (
        activeInspection ? (
          <InspectionFlow
            key={inspectionTargetKey(activeInspection.target)}
            projectId={selectedProject.id}
            roomId={selectedRoom.id}
            target={activeInspection.target}
            inspectionId={activeInspection.inspectionId}
            onExit={closeInspectionFlow}
            onCreated={(inspectionId) =>
              setActiveInspection({ target: activeInspection.target, inspectionId })
            }
          />
        ) : inspectionTarget ? (
          <InspectionList
            key={listVersion}
            projectId={selectedProject.id}
            roomId={selectedRoom.id}
            target={inspectionTarget}
            onStart={(target) => openInspection(target, null)}
            onOpen={(inspectionId) => openInspection(inspectionTarget, inspectionId)}
          />
        ) : (
        <>
          <article aria-label="room-detail" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="font-bold text-slate-900 text-base">{selectedRoom.name}</h2>
                {selectedRoom.description && (
                  <p className="text-xs text-slate-500 mt-0.5">{selectedRoom.description}</p>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-wrap justify-end">
                {selectedRoom.is_archived && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                    {t.common.archived_badge}
                  </span>
                )}
                <button
                  type="button"
                  aria-label="edit-room-detail"
                  onClick={() => startEditRoom(selectedRoom)}
                  className="text-xs px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                >
                  {t.common.edit}
                </button>
              </div>
            </div>

            {/* Room Dimensions & Calculations Summary */}
            {roomHasDraftDimensions || selectedRoom.calculations ? (
              <div
                aria-label="room-calculations-summary"
                className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 space-y-2.5 text-xs"
              >
                <div className="flex items-center justify-between border-b border-slate-200 pb-2 flex-wrap gap-1">
                  <span className="font-semibold text-slate-700">{t.rooms.calculations}:</span>
                  {selectedRoom.length && selectedRoom.width && selectedRoom.height && (
                    <span className="font-bold text-slate-900 bg-white px-2 py-0.5 rounded border border-slate-200">
                      {formatMetric(selectedRoom.length)} × {formatMetric(selectedRoom.width)} × {formatMetric(selectedRoom.height)} {t.common.unit_m}
                    </span>
                  )}
                </div>

                {/* Primary Wall Finishing Result: Gross - Deductions = Net */}
                <div className="bg-white border border-emerald-100 rounded-xl p-3 shadow-xs space-y-2">
                  <div className="flex items-baseline justify-between flex-wrap gap-1">
                    <span className="text-slate-600 font-medium text-xs">{t.rooms.net_wall_area}</span>
                    <strong className="text-emerald-700 text-base sm:text-lg font-extrabold tracking-tight">
                      {formatMetric(selectedRoom.calculations?.net_wall_area ?? selectedRoom.calculations?.total_wall_area)} {t.common.unit_m2}
                    </strong>
                  </div>
                  <div className="flex items-center gap-2 pt-1 border-t border-slate-100 text-[11px] text-slate-500 flex-wrap">
                    <span>
                      {t.rooms.total_wall_area}: <strong className="text-slate-800 font-semibold">{formatMetric(selectedRoom.calculations?.total_wall_area)} {t.common.unit_m2}</strong>
                    </span>
                    <span className="text-slate-300 font-bold">−</span>
                    <span>
                      {t.rooms.total_deductions}: <strong className="text-slate-700 font-semibold">{formatMetric(selectedRoom.calculations?.total_deduction_area ?? '0.000')} {t.common.unit_m2}</strong>
                    </span>
                  </div>
                  {typeof selectedRoom.calculations?.wall_count === 'number' && (
                    <div className="flex items-center gap-2 pt-1 text-[11px] text-slate-500">
                      <span>
                        {t.rooms.wall_count}: <strong className="text-slate-800 font-semibold">{selectedRoom.calculations.wall_count}</strong>
                      </span>
                    </div>
                  )}
                </div>

                {/* Secondary Plane Metrics: Floor, Ceiling, Perimeter */}
                <div className="grid grid-cols-3 gap-2 text-slate-600">
                  <div className="bg-white p-2 rounded-lg border border-slate-100">
                    <span className="block text-slate-400 text-[11px]">{t.rooms.floor_area}</span>
                    <strong className="text-slate-800 text-xs sm:text-sm font-semibold">
                      {formatMetric(selectedRoom.calculations?.floor_area)} {t.common.unit_m2}
                    </strong>
                  </div>
                  <div className="bg-white p-2 rounded-lg border border-slate-100">
                    <span className="block text-slate-400 text-[11px]">{t.rooms.ceiling_area}</span>
                    <strong className="text-slate-800 text-xs sm:text-sm font-semibold">
                      {formatMetric(selectedRoom.calculations?.ceiling_area)} {t.common.unit_m2}
                    </strong>
                  </div>
                  <div className="bg-white p-2 rounded-lg border border-slate-100">
                    <span className="block text-slate-400 text-[11px]">{t.rooms.perimeter}</span>
                    <strong className="text-slate-800 text-xs sm:text-sm font-semibold">
                      {formatMetric(selectedRoom.calculations?.perimeter)} {t.common.unit_m}
                    </strong>
                  </div>
                </div>
              </div>
            ) : (
              <div
                aria-label="room-unmeasured-notice"
                className="bg-slate-50 border border-dashed border-slate-200 rounded-xl p-4 text-center text-xs text-slate-500 space-y-2"
              >
                <p>{t.rooms.not_measured}</p>
                <button
                  type="button"
                  aria-label="measure-room-action"
                  onClick={
                    roomMeasurementMode === 'CUSTOM'
                      ? () => {
                          const target = document.getElementById('custom-wall-entry');
                          if (target && typeof target.scrollIntoView === 'function') {
                            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                          }
                        }
                      : () => startEditRoom(selectedRoom)
                  }
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-700 font-semibold rounded-xl hover:bg-blue-100 transition"
                >
                  + {roomMeasurementMode === 'CUSTOM'
                    ? t.rooms.start_wall_measurement
                    : t.rooms.enter_dimensions}
                </button>
              </div>
            )}
          </article>

          {/* Edit Room Form inside Room Detail View */}
          {showRoomForm && (
            <form
              aria-label="room-edit-form"
              onSubmit={handleRoomSubmit}
              className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3"
            >
              <h4 className="font-semibold text-slate-900 text-sm">{t.rooms.edit}</h4>
              <input
                aria-label="room-edit-name"
                required
                maxLength={255}
                placeholder={t.rooms.name}
                value={roomForm.name}
                onChange={(e) => setRoomForm((cur) => ({ ...cur, name: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              />
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t.rooms.length}</label>
                  <input
                    aria-label="room-edit-length"
                    type="number"
                    inputMode="decimal"
                    min="0.001"
                    step="0.001"
                    placeholder="5.000"
                    value={roomForm.length}
                    onChange={(e) => setRoomForm((cur) => ({ ...cur, length: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t.rooms.width}</label>
                  <input
                    aria-label="room-edit-width"
                    type="number"
                    inputMode="decimal"
                    min="0.001"
                    step="0.001"
                    placeholder="4.000"
                    value={roomForm.width}
                    onChange={(e) => setRoomForm((cur) => ({ ...cur, width: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t.rooms.height}</label>
                  <input
                    aria-label="room-edit-height"
                    type="number"
                    inputMode="decimal"
                    min="0.001"
                    step="0.001"
                    placeholder="2.700"
                    value={roomForm.height}
                    onChange={(e) => setRoomForm((cur) => ({ ...cur, height: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs"
                  />
                </div>
              </div>
              <textarea
                aria-label="room-edit-description"
                maxLength={4096}
                placeholder={t.rooms.description}
                value={roomForm.description}
                onChange={(e) => setRoomForm((cur) => ({ ...cur, description: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-16"
              />
              {roomFormError && (
                <p role="alert" className="text-sm text-red-600 font-medium">{roomFormError}</p>
              )}
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={() => setShowRoomForm(false)}
                  className="px-3 py-1.5 text-sm rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
                >
                  {t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={savingRoom}
                  className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
                >
                  {savingRoom ? t.common.saving : t.common.save}
                </button>
              </div>
            </form>
          )}

          <section
            aria-label="room-inspection-entry"
            className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-2.5"
          >
            <h4 className="text-sm font-semibold text-slate-900">{t.inspections.title}</h4>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                aria-label="inspect-room"
                onClick={() => openInspectionList({ kind: 'room' })}
                className="min-h-11 w-full text-xs px-2 rounded-lg bg-violet-50 text-violet-800 font-semibold hover:bg-violet-100 transition"
              >
                {t.inspections.inspect_room}
              </button>
              <button
                type="button"
                aria-label="inspect-floor"
                onClick={() => openInspectionList({ kind: 'plane', plane: 'FLOOR' })}
                className="min-h-11 w-full text-xs px-2 rounded-lg bg-violet-50 text-violet-800 font-semibold hover:bg-violet-100 transition"
              >
                {t.inspections.inspect_floor}
              </button>
              <button
                type="button"
                aria-label="inspect-ceiling"
                onClick={() => openInspectionList({ kind: 'plane', plane: 'CEILING' })}
                className="min-h-11 w-full text-xs px-2 rounded-lg bg-violet-50 text-violet-800 font-semibold hover:bg-violet-100 transition"
              >
                {t.inspections.inspect_ceiling}
              </button>
            </div>
          </section>

          <AreaSegmentList
            projectId={selectedProject.id}
            roomId={selectedRoom.id}
            onMeasurementChanged={refreshSelectedRoom}
          />

          <SurfaceList
            projectId={selectedProject.id}
            roomId={selectedRoom.id}
            roomHeight={selectedRoom.height}
            hasRoomDimensions={
              selectedRoom.length !== null && selectedRoom.length !== undefined &&
              selectedRoom.width !== null && selectedRoom.width !== undefined &&
              selectedRoom.height !== null && selectedRoom.height !== undefined
            }
            wallMode={roomMeasurementMode}
            onMeasurementChanged={refreshSelectedRoom}
            onInspectSurface={(surfaceId, surfaceName) =>
              openInspectionList({ kind: 'surface', surfaceId, surfaceName })
            }
          />
        </>
        )
      )}

      {!selectedProject && loading && (
        <p className="text-sm text-slate-500 text-center py-4">{t.projects.loading}</p>
      )}
      {!selectedProject && !loading && error && (
        <p role="alert" className="text-sm text-red-600 text-center py-4">{error}</p>
      )}
      {!selectedProject && !loading && !error && projects.length === 0 && (
        <p aria-label="no-projects" className="text-sm text-slate-400 text-center py-6">
          {t.projects.empty}
        </p>
      )}
      {!selectedProject && !loading && !error && projects.length > 0 && (
        <ul aria-label="projects-list" className="space-y-2">
          {projects.map((project) => (
            <li
              key={project.id}
              aria-label={`project-item-${project.id}`}
              className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-slate-900 text-sm">{project.name}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">
                      {statusLabel(project.status)}
                    </span>
                    {project.is_archived && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                        {t.common.archived_badge}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">{project.address}, {project.city}</p>
                  <p className="text-xs text-slate-500 mt-1">{t.projects.client}: {assignedClientName(project)}</p>
                </div>
                <div className="flex gap-1.5 flex-wrap justify-end">
                  <button
                    type="button"
                    aria-label={`open-project-${project.id}`}
                    onClick={() => openProject(project)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
                  >
                    {t.common.open}
                  </button>
                  <button
                    type="button"
                    aria-label={`edit-project-${project.id}`}
                    onClick={() => startEdit(project)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                  >
                    {t.common.edit}
                  </button>
                  <button
                    type="button"
                    aria-label={`${project.is_archived ? 'restore' : 'archive'}-project-${project.id}`}
                    onClick={() => void changeArchiveState(project)}
                    className="text-xs px-2.5 py-1 rounded-lg bg-slate-50 text-slate-600 font-medium hover:bg-slate-100 transition"
                  >
                    {project.is_archived ? t.common.restore : t.common.archive}
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
