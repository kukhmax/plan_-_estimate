import { FormEvent, useCallback, useEffect, useState } from 'react';
import { fetchClients } from '../api/clients';
import {
  archiveProject,
  createProject,
  fetchProjects,
  restoreProject,
  updateProject,
} from '../api/projects';
import { useI18n } from '../hooks/useI18n';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { ClientType } from '../types/client';
import {
  ProjectCreatePayload,
  ProjectStatus,
  ProjectType,
} from '../types/project';
import { RoomType } from '../types/room';
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

export function ProjectWorkspace() {
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

  const openProject = (project: ProjectType) => {
    closeForm();
    setSelectedProject(project);
    setSelectedRoom(null);
    setSuccess(null);
  };

  const backToProjects = () => {
    closeForm();
    setSelectedProject(null);
    setSelectedRoom(null);
    setSuccess(null);
  };

  const isBackButtonVisible = selectedProject !== null;

  useTelegramBackButton(isBackButtonVisible, () => {
    if (selectedRoom) {
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
                onClick={() => setSelectedRoom(null)}
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
          <RoomList projectId={selectedProject.id} onOpenRoom={setSelectedRoom} />
        </>
      )}

      {selectedProject && selectedRoom && (
        <>
          <article aria-label="room-detail" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-bold text-slate-900">{selectedRoom.name}</h2>
              {selectedRoom.is_archived && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium">
                  {t.common.archived_badge}
                </span>
              )}
            </div>
            {selectedRoom.description && <p className="text-sm text-slate-600 mt-2">{selectedRoom.description}</p>}
          </article>
          <SurfaceList projectId={selectedProject.id} roomId={selectedRoom.id} />
        </>
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
