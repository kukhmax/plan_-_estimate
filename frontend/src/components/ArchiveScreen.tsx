import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArchivedRoomItem, ArchivedSurfaceItem, fetchArchivedStructure } from '../api/archiveStructure';
import { ApiError } from '../api/http';
import { fetchClients, restoreClient } from '../api/clients';
import { fetchProjects, restoreProject } from '../api/projects';
import { restoreRoom } from '../api/rooms';
import { restoreSurface } from '../api/surfaces';
import { useI18n } from '../hooks/useI18n';
import { ClientType } from '../types/client';
import { ProjectType } from '../types/project';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { ArchiveClientDelete } from './ArchiveClientDelete';
import { ArchiveProjectDelete } from './ArchiveProjectDelete';
import { ArchivePhotos } from './ArchivePhotos';
import { Ico } from './Ico';

type ArchiveTab = 'clients' | 'projects' | 'rooms' | 'surfaces' | 'photos';
type RestoreKind = 'clients' | 'projects' | 'rooms' | 'surfaces';

function clientName(client: ClientType): string {
  if (client.client_type === 'COMPANY') return client.company_name ?? '—';
  return [client.first_name, client.last_name].filter(Boolean).join(' ') || '—';
}

const rowClass = 'bg-white border border-slate-200 rounded-2xl p-3 shadow-sm space-y-2';
const restoreButtonClass =
  'w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition disabled:opacity-50';

/**
 * The archive (Stage 16K.5): what the owner put away — clients, objects, and (archive cleanup AC-4a) rooms and surfaces of all
 * objects, and the photos — in one place, with the way back. The lists of clients and objects show only what is in work; "restore"
 * is here. An archived client can also be deleted for good (AC-5a), after the server has checked it has no objects.
 */
export function ArchiveScreen() {
  const { t } = useI18n();
  const text = t.archive;
  const [tab, setTab] = useState<ArchiveTab>('clients');
  const [clients, setClients] = useState<ClientType[] | null>(null);
  const [projects, setProjects] = useState<ProjectType[] | null>(null);
  const [rooms, setRooms] = useState<ArchivedRoomItem[] | null>(null);
  const [surfaces, setSurfaces] = useState<ArchivedSurfaceItem[] | null>(null);
  const [structureTotals, setStructureTotals] = useState<{ rooms: number; surfaces: number } | null>(null);
  const [photoTotals, setPhotoTotals] = useState<{ archived: number; trashed: number } | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [structureFailed, setStructureFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deletingClientId, setDeletingClientId] = useState<string | null>(null);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  // changes when an object is deleted: its photos went with it, so the photo tab reads its lists again
  const [photosKey, setPhotosKey] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    setStructureFailed(false);
    try {
      const [clientData, projectData] = await Promise.all([fetchClients({ include_archived: true }), fetchProjects(true)]);
      setClients(clientData.items.filter((client) => client.is_archived));
      setProjects(projectData.items.filter((project) => project.is_archived));
    } catch {
      setLoadFailed(true);
    }
    // apart: the rooms and surfaces failing must not hide the clients and objects
    try {
      const structure = await fetchArchivedStructure();
      setRooms(structure.rooms);
      setSurfaces(structure.surfaces);
      setStructureTotals({ rooms: structure.rooms_total, surfaces: structure.surfaces_total });
    } catch {
      setStructureFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const restore = async (kind: RestoreKind, id: string) => {
    if (busyId) return;
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      if (kind === 'clients') {
        await restoreClient(id);
        setClients((current) => (current ? current.filter((client) => client.id !== id) : current));
        setNotice(text.restored_client);
      } else if (kind === 'projects') {
        await restoreProject(id);
        setProjects((current) => (current ? current.filter((project) => project.id !== id) : current));
        setNotice(text.restored_project);
      } else if (kind === 'rooms') {
        const room = rooms?.find((entry) => entry.id === id);
        if (!room) return;
        await restoreRoom(room.project_id, room.id);
        setRooms((current) => (current ? current.filter((entry) => entry.id !== id) : current));
        setStructureTotals((current) => (current ? { ...current, rooms: Math.max(0, current.rooms - 1) } : current));
        setNotice(text.restored_room);
      } else {
        const surface = surfaces?.find((entry) => entry.id === id);
        if (!surface) return;
        await restoreSurface(surface.project_id, surface.room_id, surface.id);
        setSurfaces((current) => (current ? current.filter((entry) => entry.id !== id) : current));
        setStructureTotals((current) => (current ? { ...current, surfaces: Math.max(0, current.surfaces - 1) } : current));
        setNotice(text.restored_surface);
      }
    } catch (caught) {
      // a floor / ceiling cannot come back while the room already has an active one (409)
      setError(kind === 'surfaces' && caught instanceof ApiError && caught.status === 409 ? text.error_restore_surface_conflict : text.error_restore);
    } finally {
      setBusyId(null);
    }
  };

  const surfaceLabels = useMemo(() => ({ wall: t.surfaces.wall, floor: t.surfaces.floor, ceiling: t.surfaces.ceiling }), [t]);

  const countOf = (value: ArchiveTab): number | undefined => {
    switch (value) {
      case 'clients':
        return clients?.length;
      case 'projects':
        return projects?.length;
      case 'rooms':
        return structureTotals?.rooms;
      case 'surfaces':
        return structureTotals?.surfaces;
      default:
        return photoTotals ? photoTotals.archived + photoTotals.trashed : undefined;
    }
  };

  const tabButton = (value: ArchiveTab, label: string) => {
    const count = countOf(value);
    return (
      <button
        key={value}
        type="button"
        role="tab"
        aria-selected={tab === value}
        aria-label={`archive-tab-${value}`}
        onClick={() => {
          setTab(value);
          setNotice(null);
          setError(null);
          setDeletingClientId(null);
          setDeletingProjectId(null);
        }}
        className={`min-h-11 px-4 text-sm font-semibold rounded-xl transition ${
          tab === value ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
        }`}
      >
        {label}
        {count !== undefined && <span aria-label={`archive-count-${value}`}> ({count})</span>}
      </button>
    );
  };

  const restoreButton = (kind: RestoreKind, id: string, ariaLabel: string) => (
    <button type="button" aria-label={ariaLabel} disabled={busyId !== null} onClick={() => void restore(kind, id)} className={restoreButtonClass}>
      {busyId === id ? text.restoring : text.restore}
    </button>
  );

  const retry = (onRetry: () => void, ariaLabel: string, message: string) => (
    <div className="space-y-2">
      <p role="alert" className="text-sm text-red-600 break-words">{message}</p>
      <button type="button" aria-label={ariaLabel} onClick={onRetry} className="w-full min-h-11 px-4 text-sm font-semibold rounded-xl bg-blue-600 text-white">
        <Ico>🔄</Ico>{text.retry}
      </button>
    </div>
  );

  const structureTab = tab === 'rooms' || tab === 'surfaces';
  const waitingFor =
    tab === 'clients' ? clients : tab === 'projects' ? projects : tab === 'rooms' ? rooms : tab === 'surfaces' ? surfaces : [];

  return (
    <section aria-label="archive-section" className="w-full mt-4 space-y-3">
      <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{text.title}</h2>
      <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>

      <div role="tablist" aria-label="archive-tabs" className="flex flex-wrap gap-2">
        {tabButton('clients', text.clients_tab)}
        {tabButton('projects', text.projects_tab)}
        {tabButton('rooms', text.rooms_tab)}
        {tabButton('surfaces', text.surfaces_tab)}
        {tabButton('photos', text.photos_tab)}
      </div>

      {notice && <p role="status" className="text-sm text-emerald-700 break-words">{notice}</p>}
      {error && <p role="alert" className="text-sm text-red-600 break-words">{error}</p>}

      {/* the photos load by themselves (and stay mounted, so the count of the tab is there before it is opened) */}
      <ArchivePhotos key={photosKey} active={tab === 'photos'} onTotals={setPhotoTotals} />

      {tab !== 'photos' && !structureTab && loadFailed && retry(() => void load(), 'archive-retry', text.error_load)}
      {structureTab && structureFailed && retry(() => void load(), 'archive-retry', text.error_load)}

      {tab !== 'photos' && !(structureTab ? structureFailed : loadFailed) && waitingFor === null && (
        <p className="text-sm text-slate-500">{t.clients.loading}</p>
      )}

      {!loadFailed && tab === 'clients' && clients !== null && (
        clients.length === 0 ? (
          <p aria-label="archive-empty-clients" className="text-sm text-slate-400 text-center py-6">{text.empty_clients}</p>
        ) : (
          <ul aria-label="archive-clients-list" className="space-y-2">
            {clients.map((client) => (
              <li key={client.id} aria-label={`archived-client-${client.id}`} className={rowClass}>
                <p className="font-semibold text-slate-900 text-sm break-words">{clientName(client)}</p>
                {restoreButton('clients', client.id, `restore-client-${client.id}`)}
                {deletingClientId === client.id ? (
                  <ArchiveClientDelete
                    clientId={client.id}
                    clientName={clientName(client)}
                    onCancel={() => setDeletingClientId(null)}
                    onDeleted={() => {
                      setDeletingClientId(null);
                      setClients((current) => (current ? current.filter((entry) => entry.id !== client.id) : current));
                      setNotice(text.client_deleted);
                    }}
                  />
                ) : (
                  <button
                    type="button"
                    aria-label={`delete-client-${client.id}`}
                    disabled={busyId !== null}
                    onClick={() => {
                      setNotice(null);
                      setError(null);
                      setDeletingClientId(client.id);
                    }}
                    className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-red-300 text-red-700 transition disabled:opacity-50"
                  >
                    <Ico>🗑️</Ico>{text.client_delete}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )
      )}

      {!loadFailed && tab === 'projects' && projects !== null && (
        projects.length === 0 ? (
          <p aria-label="archive-empty-projects" className="text-sm text-slate-400 text-center py-6">{text.empty_projects}</p>
        ) : (
          <ul aria-label="archive-projects-list" className="space-y-2">
            {projects.map((project) => (
              <li key={project.id} aria-label={`archived-project-${project.id}`} className={rowClass}>
                <p className="font-semibold text-slate-900 text-sm break-words">{project.name}</p>
                <p className="text-xs text-slate-500 break-words">{[project.address, project.city].filter(Boolean).join(', ')}</p>
                {restoreButton('projects', project.id, `restore-project-${project.id}`)}
                {deletingProjectId === project.id ? (
                  <ArchiveProjectDelete
                    projectId={project.id}
                    projectName={project.name}
                    onCancel={() => setDeletingProjectId(null)}
                    onDeleted={(result) => {
                      setDeletingProjectId(null);
                      setProjects((current) => (current ? current.filter((entry) => entry.id !== project.id) : current));
                      setNotice(result.storage_pending > 0 ? text.project_deleted_pending : text.project_deleted);
                      // the rooms, surfaces and photos of the object went with it: read the lists again
                      setPhotosKey((value) => value + 1);
                      void load();
                    }}
                  />
                ) : (
                  <button
                    type="button"
                    aria-label={`delete-project-${project.id}`}
                    disabled={busyId !== null}
                    onClick={() => {
                      setNotice(null);
                      setError(null);
                      setDeletingProjectId(project.id);
                    }}
                    className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-red-300 text-red-700 transition disabled:opacity-50"
                  >
                    <Ico>🗑️</Ico>{text.project_delete}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )
      )}

      {!structureFailed && tab === 'rooms' && rooms !== null && (
        rooms.length === 0 ? (
          <p aria-label="archive-empty-rooms" className="text-sm text-slate-400 text-center py-6">{text.empty_rooms}</p>
        ) : (
          <>
            <ul aria-label="archive-rooms-list" className="space-y-2">
              {rooms.map((room) => (
                <li key={room.id} aria-label={`archived-room-${room.id}`} className={rowClass}>
                  <p className="font-semibold text-slate-900 text-sm break-words">{room.name}</p>
                  <p className="text-xs text-slate-500 break-words">{text.of_object.replace('{name}', room.project_name)}</p>
                  {restoreButton('rooms', room.id, `restore-room-${room.id}`)}
                </li>
              ))}
            </ul>
            {structureTotals && structureTotals.rooms > rooms.length && (
              <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">
                {text.structure_shown.replace('{shown}', String(rooms.length)).replace('{total}', String(structureTotals.rooms))}
              </p>
            )}
          </>
        )
      )}

      {!structureFailed && tab === 'surfaces' && surfaces !== null && (
        surfaces.length === 0 ? (
          <p aria-label="archive-empty-surfaces" className="text-sm text-slate-400 text-center py-6">{text.empty_surfaces}</p>
        ) : (
          <>
            <ul aria-label="archive-surfaces-list" className="space-y-2">
              {surfaces.map((surface) => (
                <li key={surface.id} aria-label={`archived-surface-${surface.id}`} className={rowClass}>
                  <p className="font-semibold text-slate-900 text-sm break-words">
                    {getSurfaceDisplayName({ name: surface.name, surface_type: surface.surface_type }, surfaceLabels)}
                  </p>
                  <p className="text-xs text-slate-500 break-words">
                    {text.of_room.replace('{project}', surface.project_name).replace('{room}', surface.room_name)}
                  </p>
                  {restoreButton('surfaces', surface.id, `restore-surface-${surface.id}`)}
                </li>
              ))}
            </ul>
            {structureTotals && structureTotals.surfaces > surfaces.length && (
              <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">
                {text.structure_shown.replace('{shown}', String(surfaces.length)).replace('{total}', String(structureTotals.surfaces))}
              </p>
            )}
          </>
        )
      )}
    </section>
  );
}
