import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArchivedRoomItem, ArchivedSurfaceItem, fetchArchivedStructure } from '../api/archiveStructure';
import { ArchivedInspectionItem, fetchArchivedInspections } from '../api/archiveInspections';
import { ApiError } from '../api/http';
import { restoreInspection } from '../api/inspections';
import { fetchClients, restoreClient } from '../api/clients';
import { fetchProjects, restoreProject } from '../api/projects';
import { fetchArchivedDocuments } from '../api/archivedDocuments';
import { fetchArchivedPayments, restorePayment } from '../api/payments';
import { restoreRoom } from '../api/rooms';
import {
  fetchInspectionPurgePreview,
  fetchRoomPurgePreview,
  fetchSurfacePurgePreview,
  purgeInspection,
  purgeRoom,
  purgeSurface,
} from '../api/structurePurge';
import { restoreSurface } from '../api/surfaces';
import { useI18n } from '../hooks/useI18n';
import { ClientType } from '../types/client';
import type { ArchivedDocumentItem } from '../types/archivedDocument';
import type { ArchivedPaymentItem } from '../types/payment';
import { ProjectType } from '../types/project';
import { archivedDocumentKindLabel } from '../utils/archivedDocumentFormat';
import { formatIssued } from '../utils/documentFormat';
import { formatDay, formatMoney } from '../utils/paymentFormat';
import { getSurfaceDisplayName } from '../utils/surfaceDisplayName';
import { ArchiveClientDelete } from './ArchiveClientDelete';
import { ArchiveDocumentDelete } from './ArchiveDocumentDelete';
import { ArchivePaymentDelete } from './ArchivePaymentDelete';
import { ArchiveProjectDelete } from './ArchiveProjectDelete';
import { ArchiveStructureDelete } from './ArchiveStructureDelete';
import { ArchivePhotos } from './ArchivePhotos';
import { Ico } from './Ico';

type ArchiveTab = 'clients' | 'projects' | 'rooms' | 'surfaces' | 'inspections' | 'payments' | 'documents' | 'photos';
type RestoreKind = 'clients' | 'projects' | 'rooms' | 'surfaces' | 'inspections' | 'payments';

function clientName(client: ClientType): string {
  if (client.client_type === 'COMPANY') return client.company_name ?? '—';
  return [client.first_name, client.last_name].filter(Boolean).join(' ') || '—';
}

const rowClass = 'pe-card rounded-2xl p-3 shadow-sm space-y-2';
const restoreButtonClass =
  'w-full min-h-11 px-3 text-sm font-semibold rounded-xl bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition disabled:opacity-50';

/**
 * The archive (Stage 16K.5): what the owner put away — clients, objects, and (archive cleanup AC-4a) rooms and surfaces of all
 * objects, the inspections (AC-7), and the photos — in one place, with the way back. The lists of clients and objects show only what is in work; "restore"
 * is here. An archived client can also be deleted for good (AC-5a), after the server has checked it has no objects.
 */
export function ArchiveScreen() {
  const { t, locale } = useI18n();
  const text = t.archive;
  const [tab, setTab] = useState<ArchiveTab>('clients');
  const [clients, setClients] = useState<ClientType[] | null>(null);
  const [projects, setProjects] = useState<ProjectType[] | null>(null);
  const [rooms, setRooms] = useState<ArchivedRoomItem[] | null>(null);
  const [surfaces, setSurfaces] = useState<ArchivedSurfaceItem[] | null>(null);
  const [inspections, setInspections] = useState<ArchivedInspectionItem[] | null>(null);
  const [inspectionsTotal, setInspectionsTotal] = useState(0);
  const [inspectionsFailed, setInspectionsFailed] = useState(false);
  const [deletingInspectionId, setDeletingInspectionId] = useState<string | null>(null);
  const [payments, setPayments] = useState<ArchivedPaymentItem[] | null>(null);
  const [paymentsTotal, setPaymentsTotal] = useState(0);
  const [paymentsFailed, setPaymentsFailed] = useState(false);
  const [deletingPaymentId, setDeletingPaymentId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<ArchivedDocumentItem[] | null>(null);
  const [documentsTotal, setDocumentsTotal] = useState(0);
  const [documentsFailed, setDocumentsFailed] = useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null);
  const [structureTotals, setStructureTotals] = useState<{ rooms: number; surfaces: number } | null>(null);
  const [photoTotals, setPhotoTotals] = useState<{ archived: number; trashed: number } | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [structureFailed, setStructureFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deletingClientId, setDeletingClientId] = useState<string | null>(null);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [deletingStructureId, setDeletingStructureId] = useState<string | null>(null);
  // changes when an object is deleted: its photos went with it, so the photo tab reads its lists again
  const [photosKey, setPhotosKey] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadFailed(false);
    setStructureFailed(false);
    setInspectionsFailed(false);
    setPaymentsFailed(false);
    setDocumentsFailed(false);
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
    // apart again: the inspections failing must not hide the rooms and surfaces
    try {
      const found = await fetchArchivedInspections();
      setInspections(found.items);
      setInspectionsTotal(found.total);
    } catch {
      setInspectionsFailed(true);
    }
    // and the settlement records: apart too
    try {
      const found = await fetchArchivedPayments();
      setPayments(found.items);
      setPaymentsTotal(found.total);
    } catch {
      setPaymentsFailed(true);
    }
    // and the contracts and protocols: apart too
    try {
      const found = await fetchArchivedDocuments();
      setDocuments(found.items);
      setDocumentsTotal(found.total);
    } catch {
      setDocumentsFailed(true);
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
      } else if (kind === 'payments') {
        const record = payments?.find((entry) => entry.id === id);
        if (!record) return;
        await restorePayment(record.project_id, record.id);
        setPayments((current) => (current ? current.filter((entry) => entry.id !== id) : current));
        setPaymentsTotal((current) => Math.max(0, current - 1));
        setNotice(text.restored_payment);
      } else if (kind === 'inspections') {
        const inspection = inspections?.find((entry) => entry.id === id);
        if (!inspection) return;
        await restoreInspection(inspection.project_id, inspection.room_id, inspection.id);
        setInspections((current) => (current ? current.filter((entry) => entry.id !== id) : current));
        setInspectionsTotal((current) => Math.max(0, current - 1));
        setNotice(text.restored_inspection);
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
      case 'inspections':
        return inspections === null ? undefined : inspectionsTotal;
      case 'payments':
        return payments === null ? undefined : paymentsTotal;
      case 'documents':
        return documents === null ? undefined : documentsTotal;
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
          setDeletingStructureId(null);
          setDeletingInspectionId(null);
          setDeletingPaymentId(null);
          setDeletingDocumentId(null);
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

  const deleteStructureButton = (ariaLabel: string, id: string) => (
    <button
      type="button"
      aria-label={ariaLabel}
      disabled={busyId !== null}
      onClick={() => {
        setNotice(null);
        setError(null);
        setDeletingStructureId(id);
      }}
      className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-red-300 text-red-700 transition disabled:opacity-50"
    >
      <Ico>🗑️</Ico>{text.client_delete}
    </button>
  );

  // a room / surface was deleted for good: it leaves its list, the number goes down, and the photo tab reads its lists again
  const afterStructureDeleted = (kind: 'rooms' | 'surfaces', id: string, storagePending: number) => {
    setDeletingStructureId(null);
    if (kind === 'rooms') setRooms((current) => (current ? current.filter((entry) => entry.id !== id) : current));
    else setSurfaces((current) => (current ? current.filter((entry) => entry.id !== id) : current));
    setStructureTotals((current) => (current ? { ...current, [kind]: Math.max(0, current[kind] - 1) } : current));
    setNotice(storagePending > 0 ? text.structure_deleted_pending : kind === 'rooms' ? text.structure_deleted_room : text.structure_deleted_surface);
    setPhotosKey((value) => value + 1);
  };

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
    tab === 'clients' ? clients : tab === 'projects' ? projects : tab === 'rooms' ? rooms : tab === 'surfaces' ? surfaces
      : tab === 'inspections' ? inspections : tab === 'payments' ? payments : tab === 'documents' ? documents : [];

  // where the inspection was made: the wall by its name, the floor / ceiling, or the room itself
  const inspectionTitle = (item: ArchivedInspectionItem): string => {
    if (item.surface_id && item.surface_name && item.surface_type) {
      return getSurfaceDisplayName({ name: item.surface_name, surface_type: item.surface_type }, surfaceLabels);
    }
    if (item.plane === 'FLOOR') return t.surfaces.floor;
    if (item.plane === 'CEILING') return t.surfaces.ceiling;
    return t.inspections.inspect_room;
  };
  const substrateText = (value: string): string => String((t.inspections as Record<string, unknown>)[`substrate_${value.toLowerCase()}`] ?? value);

  return (
    <section aria-label="archive-section" className="w-full mt-4 space-y-3">
      <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{text.title}</h2>
      <p className="text-sm text-[var(--tg-theme-hint-color)] break-words">{text.intro}</p>

      <div role="tablist" aria-label="archive-tabs" className="flex flex-wrap gap-2">
        {tabButton('clients', text.clients_tab)}
        {tabButton('projects', text.projects_tab)}
        {tabButton('rooms', text.rooms_tab)}
        {tabButton('surfaces', text.surfaces_tab)}
        {tabButton('inspections', text.inspections_tab)}
        {tabButton('payments', text.payments_tab)}
        {tabButton('documents', text.documents_tab)}
        {tabButton('photos', text.photos_tab)}
      </div>

      {notice && <p role="status" className="text-sm text-emerald-700 break-words">{notice}</p>}
      {error && <p role="alert" className="text-sm text-red-600 break-words">{error}</p>}

      {/* the photos load by themselves (and stay mounted, so the count of the tab is there before it is opened) */}
      <ArchivePhotos key={photosKey} active={tab === 'photos'} onTotals={setPhotoTotals} />

      {tab === 'inspections' && inspectionsFailed && retry(() => void load(), 'archive-retry', text.error_load)}
      {tab === 'payments' && paymentsFailed && retry(() => void load(), 'archive-retry', text.error_load)}
      {tab === 'documents' && documentsFailed && retry(() => void load(), 'archive-retry', text.error_load)}
      {tab !== 'photos' && tab !== 'payments' && tab !== 'documents' && tab !== 'inspections' && !structureTab && loadFailed && retry(() => void load(), 'archive-retry', text.error_load)}
      {structureTab && structureFailed && retry(() => void load(), 'archive-retry', text.error_load)}

      {tab !== 'photos' && !(tab === 'payments' ? paymentsFailed : tab === 'documents' ? documentsFailed : tab === 'inspections' ? inspectionsFailed : structureTab ? structureFailed : loadFailed) && waitingFor === null && (
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
                  {deletingStructureId === room.id ? (
                    <ArchiveStructureDelete
                      kind="ROOM"
                      name={room.name}
                      load={() => fetchRoomPurgePreview(room.project_id, room.id)}
                      run={() => purgeRoom(room.project_id, room.id)}
                      onCancel={() => setDeletingStructureId(null)}
                      onDeleted={(result) => afterStructureDeleted('rooms', room.id, result.storage_pending)}
                    />
                  ) : (
                    deleteStructureButton(`delete-room-${room.id}`, room.id)
                  )}
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
                  {deletingStructureId === surface.id ? (
                    <ArchiveStructureDelete
                      kind="SURFACE"
                      name={getSurfaceDisplayName({ name: surface.name, surface_type: surface.surface_type }, surfaceLabels)}
                      load={() => fetchSurfacePurgePreview(surface.project_id, surface.room_id, surface.id)}
                      run={() => purgeSurface(surface.project_id, surface.room_id, surface.id)}
                      onCancel={() => setDeletingStructureId(null)}
                      onDeleted={(result) => afterStructureDeleted('surfaces', surface.id, result.storage_pending)}
                    />
                  ) : (
                    deleteStructureButton(`delete-surface-${surface.id}`, surface.id)
                  )}
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

      {!inspectionsFailed && tab === 'inspections' && inspections !== null && (
        inspections.length === 0 ? (
          <p aria-label="archive-empty-inspections" className="text-sm text-slate-400 text-center py-6">{text.empty_inspections}</p>
        ) : (
          <>
            <ul aria-label="archive-inspections-list" className="space-y-2">
              {inspections.map((inspection) => (
                <li key={inspection.id} aria-label={`archived-inspection-${inspection.id}`} className={rowClass}>
                  <p className="font-semibold text-slate-900 text-sm break-words">{inspectionTitle(inspection)}</p>
                  <p className="text-xs text-slate-500 break-words">
                    {[
                      text.inspection_substrate.replace('{substrate}', substrateText(inspection.substrate)),
                      inspection.status === 'COMPLETED' ? t.inspections.status_completed : t.inspections.status_draft,
                      formatIssued(inspection.created_at, locale),
                    ].join(' · ')}
                  </p>
                  <p className="text-xs text-slate-500 break-words">
                    {text.of_room.replace('{project}', inspection.project_name).replace('{room}', inspection.room_name)}
                  </p>
                  {restoreButton('inspections', inspection.id, `restore-inspection-${inspection.id}`)}
                  {deletingInspectionId === inspection.id ? (
                    <ArchiveStructureDelete
                      kind="INSPECTION"
                      name={inspectionTitle(inspection)}
                      load={() => fetchInspectionPurgePreview(inspection.project_id, inspection.room_id, inspection.id)}
                      run={() => purgeInspection(inspection.project_id, inspection.room_id, inspection.id)}
                      onCancel={() => setDeletingInspectionId(null)}
                      onDeleted={(result) => {
                        setDeletingInspectionId(null);
                        setInspections((current) => (current ? current.filter((entry) => entry.id !== inspection.id) : current));
                        setInspectionsTotal((current) => Math.max(0, current - 1));
                        setNotice(result.storage_pending > 0 ? text.structure_deleted_pending : text.inspection_deleted);
                        // its photos went with it: the photo tab reads its lists again
                        setPhotosKey((value) => value + 1);
                      }}
                    />
                  ) : (
                    <button
                      type="button"
                      aria-label={`delete-inspection-${inspection.id}`}
                      disabled={busyId !== null}
                      onClick={() => {
                        setNotice(null);
                        setError(null);
                        setDeletingInspectionId(inspection.id);
                      }}
                      className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-red-300 text-red-700 transition disabled:opacity-50"
                    >
                      <Ico>🗑️</Ico>{text.client_delete}
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {inspectionsTotal > inspections.length && (
              <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">
                {text.structure_shown.replace('{shown}', String(inspections.length)).replace('{total}', String(inspectionsTotal))}
              </p>
            )}
          </>
        )
      )}

      {!paymentsFailed && tab === 'payments' && payments !== null && (
        payments.length === 0 ? (
          <p aria-label="archive-empty-payments" className="text-sm text-slate-400 text-center py-6">{text.empty_payments}</p>
        ) : (
          <>
            <ul aria-label="archive-payments-list" className="space-y-2">
              {payments.map((payment) => {
                const meta = [formatDay(payment.occurred_on)];
                if (payment.number) meta.push(`${t.payments.fields.number}: ${payment.number}`);
                if (payment.counterparty) meta.push(payment.counterparty);
                if (payment.category) meta.push(t.payments.category[payment.category]);
                if (payment.photos > 0) meta.push(text.payment_photos.replace('{count}', String(payment.photos)));
                return (
                  <li key={payment.id} aria-label={`archived-payment-${payment.id}`} className={rowClass}>
                    <p className="text-xs font-semibold text-slate-500">{t.payments.kind[payment.kind]}</p>
                    <p className="font-semibold text-slate-900 text-sm break-words">{payment.title}</p>
                    <p className="text-base font-bold text-slate-900 break-words">{formatMoney(payment.amount_gross)}</p>
                    <p className="text-xs text-slate-500 break-words">{meta.join(' · ')}</p>
                    <p className="text-xs text-slate-500 break-words">{text.of_object.replace('{name}', payment.project_name)}</p>
                    {restoreButton('payments', payment.id, `restore-payment-${payment.id}`)}
                    {deletingPaymentId === payment.id ? (
                      <ArchivePaymentDelete
                        payment={payment}
                        onCancel={() => setDeletingPaymentId(null)}
                        onDeleted={(result) => {
                          setDeletingPaymentId(null);
                          setPayments((current) => (current ? current.filter((entry) => entry.id !== payment.id) : current));
                          setPaymentsTotal((current) => Math.max(0, current - 1));
                          setNotice(result.storage_pending > 0 ? text.structure_deleted_pending : text.payment_deleted);
                          // its receipt photos went with it: the photo tab reads its lists again
                          setPhotosKey((value) => value + 1);
                        }}
                      />
                    ) : (
                      <button
                        type="button"
                        aria-label={`delete-payment-${payment.id}`}
                        disabled={busyId !== null}
                        onClick={() => {
                          setNotice(null);
                          setError(null);
                          setDeletingPaymentId(payment.id);
                        }}
                        className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-red-300 text-red-700 transition disabled:opacity-50"
                      >
                        <Ico>🗑️</Ico>{text.client_delete}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
            {paymentsTotal > payments.length && (
              <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">
                {text.structure_shown.replace('{shown}', String(payments.length)).replace('{total}', String(paymentsTotal))}
              </p>
            )}
          </>
        )
      )}

      {!documentsFailed && tab === 'documents' && documents !== null && (
        documents.length === 0 ? (
          <p aria-label="archive-empty-documents" className="text-sm text-slate-400 text-center py-6">{text.empty_documents}</p>
        ) : (
          <>
            <ul aria-label="archive-documents-list" className="space-y-2">
              {documents.map((entry) => {
                const meta = [
                  (entry.kind === 'CONTRACT' ? text.document_version : text.document_sequence).replace('{n}', String(entry.ordinal)),
                ];
                if (entry.number) meta.push(text.document_number.replace('{number}', entry.number));
                return (
                  <li key={`${entry.kind}-${entry.id}`} aria-label={`archived-document-${entry.id}`} className={rowClass}>
                    <p className="font-semibold text-slate-900 text-sm break-words">{archivedDocumentKindLabel(text, entry.kind)}</p>
                    <p className="text-xs text-slate-500 break-words">{meta.join(' · ')}</p>
                    <p className="text-xs text-slate-500 break-words">{text.of_object.replace('{name}', entry.project_name)}</p>
                    <p className="text-xs text-slate-500 break-words">
                      {entry.issued_at ? text.document_issued.replace('{date}', formatIssued(entry.issued_at, locale)) : text.document_draft}
                      {' · '}
                      {text.document_archived.replace('{date}', formatIssued(entry.archived_at, locale))}
                    </p>
                    {deletingDocumentId === entry.id ? (
                      <ArchiveDocumentDelete
                        document={entry}
                        onCancel={() => setDeletingDocumentId(null)}
                        onDeleted={() => {
                          setDeletingDocumentId(null);
                          setDocuments((current) => (current ? current.filter((item) => item.id !== entry.id) : current));
                          setDocumentsTotal((current) => Math.max(0, current - 1));
                          setNotice(text.document_deleted);
                        }}
                      />
                    ) : (
                      <button
                        type="button"
                        aria-label={`delete-document-${entry.id}`}
                        disabled={busyId !== null}
                        onClick={() => {
                          setNotice(null);
                          setError(null);
                          setDeletingDocumentId(entry.id);
                        }}
                        className="w-full min-h-11 px-3 text-sm font-semibold rounded-xl border border-red-300 text-red-700 transition disabled:opacity-50"
                      >
                        <Ico>🗑️</Ico>{text.client_delete}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
            {documentsTotal > documents.length && (
              <p className="break-words text-xs text-[var(--tg-theme-hint-color)]">
                {text.structure_shown.replace('{shown}', String(documents.length)).replace('{total}', String(documentsTotal))}
              </p>
            )}
          </>
        )
      )}
    </section>
  );
}
