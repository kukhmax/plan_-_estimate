import { FormEvent, useCallback, useEffect, useState } from 'react';
import { fetchClients } from '../api/clients';
import {
  archiveProject,
  createProject,
  fetchProject,
  fetchProjects,
  restoreProject,
  updateProject,
} from '../api/projects';
import { listEstimates } from '../api/estimates';
import { fetchRoom, updateRoom } from '../api/rooms';
import { useI18n } from '../hooks/useI18n';
import { resolveRoomMeasurementMode } from '../hooks/roomMeasurementMode';
import { usePhotoBackStack } from '../hooks/PhotoBackContext';
import { ProjectPhotosProvider } from '../hooks/ProjectPhotosContext';
import { useTelegramBackButton } from '../hooks/useTelegramWebApp';
import { ClientType } from '../types/client';
import {
  ProjectCreatePayload,
  ProjectStatus,
  ProjectType,
} from '../types/project';
import { RoomType, RoomUpdatePayload } from '../types/room';
import { InspectionTarget } from '../types/inspection';
import { EstimateSummaryRead } from '../types/estimate';
import { localizeApiError } from '../utils/apiErrors';
import { formatMetric } from '../utils/format';
import { AreaSegmentList } from './AreaSegmentList';
import { EstimateList } from './EstimateList';
import { EstimateShell } from './EstimateShell';
import { InspectionFlow } from './InspectionFlow';
import { InspectionList } from './InspectionList';
import { PhotoCardButton, PhotoCardPanel } from './PhotoCard';
import { RoomList } from './RoomList';
import { OpeningGroupList } from './OpeningGroupList';
import { ProjectDocuments } from './ProjectDocuments';
import { ProjectAdjacentWorks } from './ProjectAdjacentWorks';
import { ProjectAcceptance } from './ProjectAcceptance';
import { ProjectConcealedWorks } from './ProjectConcealedWorks';
import { ProjectDecisions } from './ProjectDecisions';
import { ProjectDowntime } from './ProjectDowntime';
import { ProjectContract } from './ProjectContract';
import { ProjectHandover } from './ProjectHandover';
import { ProjectRepresentatives } from './ProjectRepresentatives';
import type { UnpricedWork } from '../types/document';
import { inspectionTargetOf } from '../utils/unpricedTarget';
import { ProjectSummaryCard } from './ProjectSummaryCard';
import { DocumentsMenu, DocumentsSection, LegalMenu, LegalSection, ObjectPhotos, ObjectSection, ProjectHub } from './ProjectHub';
import { PrepareOfflineButton } from './PrepareOfflineButton';
import { ProjectNotes } from './ProjectNotes';
import { SurfaceList } from './SurfaceList';
import { KnowledgeBasis, KnowledgeBasisTarget } from './KnowledgeBasis';
import { DimensionInput } from './DimensionInput';
import { Ico } from './Ico';

/** Which document of the knowledge base's links stands behind each screen of the section "Umowa i protokoły" (Stage 17E). */
const LEGAL_BASIS: Partial<Record<LegalSection, KnowledgeBasisTarget[]>> = {
  contract: [{ kind: 'DOCUMENT', target: 'CONTRACT' }],
  handover: [{ kind: 'DOCUMENT', target: 'HANDOVER_PROTOCOL' }],
  concealed: [{ kind: 'DOCUMENT', target: 'CONCEALED_WORKS_PROTOCOL' }],
  acceptance: [{ kind: 'DOCUMENT', target: 'FINAL_PROTOCOL' }],
  decisions: [{ kind: 'DOCUMENT', target: 'DECISION_PROTOCOL' }],
  downtime: [{ kind: 'DOCUMENT', target: 'DOWNTIME_NOTICE' }, { kind: 'DOCUMENT', target: 'DOWNTIME_PROTOCOL' }],
};

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
  /** An overlay above the workspace (the account dialog) owns the Telegram BackButton while it is open. */
  backSuspended?: boolean;
  /** A request from another screen (the card of a client): open the estimates of this object. Handled once per token. */
  openRequest?: ProjectOpenRequest | null;
}

export interface ProjectOpenRequest {
  token: number;
  projectId: string;
  view: 'estimates' | 'project';
}

export function ProjectWorkspace({ resetSignal, backSuspended = false, openRequest = null }: ProjectWorkspaceProps) {
  const { t } = useI18n();
  const photoBack = usePhotoBackStack();
  const [projects, setProjects] = useState<ProjectType[]>([]);
  const [clients, setClients] = useState<ClientType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<ProjectType | null>(null);
  const [selectedRoom, setSelectedRoom] = useState<RoomType | null>(null);
  const roomDimensionsKey = `${selectedRoom?.length ?? ''}|${selectedRoom?.width ?? ''}|${selectedRoom?.height ?? ''}`;
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

  const [showEstimates, setShowEstimates] = useState(false);
  // The object is a hub of tiles (null); a tile opens one screen, and "Umowa i protokoły" opens one more level.
  const [objectSection, setObjectSection] = useState<ObjectSection | null>(null);
  const [legalSection, setLegalSection] = useState<LegalSection | null>(null);
  const [documentsSection, setDocumentsSection] = useState<DocumentsSection | null>(null);
  // Bumped after a room change so the object summary reloads (13F-PRE).
  const [summaryToken, setSummaryToken] = useState(0);
  const [selectedEstimate, setSelectedEstimate] = useState<EstimateSummaryRead | null>(null);
  const [selectedEstimateGroupKey, setSelectedEstimateGroupKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [projectData, clientData] = await Promise.all([
        fetchProjects(false),
        fetchClients({ include_archived: true }),
      ]);
      setProjects(projectData.items);
      setClients(clientData.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.projects.error);
    } finally {
      setLoading(false);
    }
  }, [t.projects.error]);

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
      setRoomFormError(err instanceof Error ? localizeApiError(err, t) : t.rooms.error);
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

  const sectionTitle = (section: ObjectSection) =>
    ({
      rooms: t.rooms.title,
      photos: t.photos.section.project_title,
      documents: t.documents.title,
      legal: t.objectHub.legal,
      summary: t.object_summary.title,
      notes: t.notes.title,
    })[section];

  const documentsTitle = (section: DocumentsSection) =>
    ({
      tech_card: t.documents.kind_tech_card,
      plan: t.documents.kind_production_plan,
      photo_report: t.documents.photo_report,
      journal: t.documents.journal_title,
    })[section];

  const legalTitle = (section: LegalSection) =>
    ({
      representatives: t.representatives.title,
      adjacent: t.adjacentWorks.title,
      contract: t.contract.title,
      handover: t.handover.title,
      concealed: t.concealed.title,
      acceptance: t.acceptance.title,
      decisions: t.decisions.title,
      downtime: t.downtime.title,
    })[section];

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

  const openProject = (project: ProjectType, section: ObjectSection | null = null) => {
    closeForm();
    setShowRoomForm(false);
    closeInspections();
    setShowEstimates(false);
    setSelectedEstimate(null);
    setSelectedEstimateGroupKey(null);
    setSelectedProject(project);
    setSelectedRoom(null);
    setObjectSection(section);
    setLegalSection(null);
    setDocumentsSection(null);
    setSuccess(null);
  };

  const openRoom = async (room: RoomType) => {
    closeForm();
    setShowRoomForm(false);
    closeInspections();
    setObjectSection('rooms');
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

  // Stage 15H.1: from a blocked photo report straight to the inspection that holds the recommendation ...
  const openRecommendationInspection = async (work: UnpricedWork) => {
    if (!selectedProject || !work.inspection_id) return;
    let room: RoomType;
    try {
      room = await fetchRoom(selectedProject.id, work.room_id);
    } catch {
      setError(t.projects.error);
      return;
    }
    const target = inspectionTargetOf(work);
    closeForm();
    setShowRoomForm(false);
    setShowEstimates(false);
    setSelectedEstimate(null);
    setSelectedEstimateGroupKey(null);
    setSelectedRoom(room);
    setSuccess(null);
    // the list is the step below the inspection, so the back button returns there, then to the room
    setInspectionTarget(target);
    setActiveInspection({ target, inspectionId: work.inspection_id });
  };

  // ... or to the estimate whose prices the report uses (the list of estimates when there is none yet).
  const openCurrentEstimate = async (estimateId: string | null) => {
    if (!selectedProject) return;
    let estimate: EstimateSummaryRead | null = null;
    if (estimateId) {
      try {
        estimate = (await listEstimates(selectedProject.id)).items.find((item) => item.id === estimateId) ?? null;
      } catch {
        estimate = null; // the list of estimates opens instead and shows its own error
      }
    }
    closeForm();
    setShowRoomForm(false);
    closeInspections();
    setSelectedRoom(null);
    setSelectedEstimateGroupKey(null);
    setSelectedEstimate(estimate);
    setShowEstimates(true);
    setSuccess(null);
  };

  const backToProjects = () => {
    closeForm();
    setShowRoomForm(false);
    closeInspections();
    setShowEstimates(false);
    setSelectedEstimate(null);
    setSelectedEstimateGroupKey(null);
    setSelectedProject(null);
    setSelectedRoom(null);
    setObjectSection(null);
    setLegalSection(null);
    setDocumentsSection(null);
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
    setShowEstimates(false);
    setSelectedEstimate(null);
    setSelectedEstimateGroupKey(null);
    setSelectedProject(null);
    setSelectedRoom(null);
    setObjectSection(null);
    setLegalSection(null);
    setDocumentsSection(null);
    setSuccess(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetSignal]);

  // One request is handled once: the effect depends on its token only.
  useEffect(() => {
    if (!openRequest) return;
    let cancelled = false;
    fetchProject(openRequest.projectId)
      .then((project) => {
        if (cancelled) return;
        openProject(project);
        if (openRequest.view === 'estimates') setShowEstimates(true);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t.projects.error);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequest?.token]);

  useTelegramBackButton(isBackButtonVisible && !backSuspended, () => {
    // An open photo viewer takes the press first (contract §8); nothing else navigates then.
    if (photoBack.closeTop()) return;
    if (showRoomForm) {
      setShowRoomForm(false);
    } else if (activeInspection) {
      setActiveInspection(null);
      setListVersion((version) => version + 1);
    } else if (inspectionTarget) {
      setInspectionTarget(null);
    } else if (selectedRoom) {
      setSelectedRoom(null);
    } else if (selectedEstimateGroupKey) {
      setSelectedEstimateGroupKey(null);
    } else if (selectedEstimate) {
      setSelectedEstimate(null);
    } else if (showEstimates) {
      setShowEstimates(false);
    } else if (legalSection) {
      setLegalSection(null);
    } else if (documentsSection) {
      setDocumentsSection(null);
    } else if (objectSection) {
      setObjectSection(null);
    } else if (selectedProject) {
      backToProjects();
    }
  });

  return (
    <ProjectPhotosProvider projectId={selectedProject?.id ?? null} backRegistry={photoBack.registry}>
    <section aria-label="projects-workspace" className="w-full mt-4">
      {selectedProject && (
        <nav aria-label="hierarchy-navigation" className="flex items-center gap-1.5 flex-wrap text-xs text-[var(--tg-theme-hint-color)] mb-3">
          <button
            type="button"
            aria-label="back-to-projects"
            onClick={backToProjects}
            className="inline-flex items-center min-h-11 pr-1 text-left break-words font-semibold text-blue-700 hover:underline"
          >
            {t.projects.title}
          </button>
          <span>/</span>
          {showEstimates || selectedRoom || objectSection ? (
            <button
              type="button"
              aria-label="back-to-project"
              onClick={() => {
                setShowEstimates(false);
                setSelectedEstimate(null);
                setSelectedRoom(null);
                setShowRoomForm(false);
                setObjectSection(null);
                setLegalSection(null);
    setDocumentsSection(null);
                closeInspections();
              }}
              className="inline-flex items-center min-h-11 pr-1 text-left break-words font-semibold text-blue-700 hover:underline"
            >
              {selectedProject.name}
            </button>
          ) : (
            <span className="font-medium text-[var(--tg-theme-text-color)]">{selectedProject.name}</span>
          )}
          {(showEstimates || selectedRoom || objectSection) && <span>/</span>}
          {showEstimates && selectedEstimate ? (
            <>
              <button
                type="button"
                aria-label="back-to-estimates"
                onClick={() => { setSelectedEstimate(null); setSelectedEstimateGroupKey(null); }}
                className="inline-flex items-center min-h-11 pr-1 text-left break-words font-semibold text-blue-700 hover:underline"
              >
                <Ico>⬅️</Ico>{t.estimates.back_to_list}
              </button>
              <span>/</span>
              <span className="font-medium text-[var(--tg-theme-text-color)]">
                {t.estimates.version} {selectedEstimate.version}
              </span>
            </>
          ) : showEstimates ? (
            <span className="font-medium text-[var(--tg-theme-text-color)]">{t.estimates.title}</span>
          ) : selectedRoom ? (
            <>
              <button
                type="button"
                aria-label="back-to-rooms"
                onClick={() => {
                  setShowRoomForm(false);
                  closeInspections();
                  setSelectedRoom(null);
                }}
                className="inline-flex items-center min-h-11 pr-1 text-left break-words font-semibold text-blue-700 hover:underline"
              >
                {t.rooms.title}
              </button>
              <span>/</span>
              <span className="font-medium text-[var(--tg-theme-text-color)]">{selectedRoom.name}</span>
              <span>/</span>
              <span>{t.surfaces.title}</span>
            </>
          ) : objectSection === 'legal' && legalSection ? (
            <>
              <button
                type="button"
                aria-label="back-to-legal"
                onClick={() => setLegalSection(null)}
                className="inline-flex items-center min-h-11 pr-1 text-left break-words font-semibold text-blue-700 hover:underline"
              >
                {t.objectHub.legal}
              </button>
              <span>/</span>
              <span className="font-medium text-[var(--tg-theme-text-color)]">{legalTitle(legalSection)}</span>
            </>
          ) : objectSection === 'documents' && documentsSection ? (
            <>
              <button
                type="button"
                aria-label="back-to-documents"
                onClick={() => setDocumentsSection(null)}
                className="inline-flex items-center min-h-11 pr-1 text-left break-words font-semibold text-blue-700 hover:underline"
              >
                {t.documents.title}
              </button>
              <span>/</span>
              <span className="font-medium text-[var(--tg-theme-text-color)]">{documentsTitle(documentsSection)}</span>
            </>
          ) : objectSection ? (
            <span className="font-medium text-[var(--tg-theme-text-color)]">{sectionTitle(objectSection)}</span>
          ) : null}
        </nav>
      )}

      {/* Object-level Estimate shortcut (13E.5B walkthrough): one shared
          action in nested room/surface views, opening the SAME project
          Estimate state as the overview card. Not shown on the overview (which
          has the large card) nor on the Estimate screens themselves. */}
      {selectedProject && selectedRoom && !showEstimates && (
        <button
          type="button"
          aria-label="open-object-estimate"
          onClick={() => {
            setShowRoomForm(false);
            closeInspections();
            setSelectedRoom(null);
            setSelectedEstimate(null);
            setSelectedEstimateGroupKey(null);
            setShowEstimates(true);
          }}
          className="w-full min-h-11 mb-3 bg-amber-500 border border-amber-600 rounded-xl px-4 flex items-center justify-between gap-2 hover:bg-amber-400 active:bg-amber-600 transition"
        >
          <span className="font-bold text-slate-950 text-sm break-words">{t.estimates.open_object_estimate}</span>
          <span aria-hidden="true" className="text-slate-950 text-lg leading-none">›</span>
        </button>
      )}

      {/* the title and "Edytuj" belong to the hub of the object; its other screens are named by the breadcrumb */}
      {!selectedRoom && !showEstimates && (!selectedProject || objectSection === null) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">
            {selectedProject ? selectedProject.name : t.projects.title}
          </h2>
          <button
            type="button"
            aria-label={selectedProject ? 'edit-project-detail' : 'add-project'}
            onClick={() => selectedProject ? startEdit(selectedProject) : startCreate()}
            className="min-h-11 px-4 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition"
          >
            <Ico>{selectedProject ? '✏️' : '➕'}</Ico>{selectedProject ? t.common.edit : t.projects.add}
          </button>
        </div>
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
              <Ico>✖️</Ico>{t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
            >
              <Ico>💾</Ico>{saving ? t.common.saving : t.common.save}
            </button>
          </div>
        </form>
      )}

      {success && <p role="status" className="text-sm text-emerald-700 mb-3">{success}</p>}
      {selectedProject && error && <p role="alert" className="text-sm text-red-600 mb-3">{error}</p>}

      {selectedProject && !selectedRoom && !showEstimates && (
        <>
          {objectSection === null && (
            <div className="space-y-3">
            <article aria-label="project-detail" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                {/* This card is an intentionally always-white surface (never
                    theme-aware) — its value text needs an explicit dark
                    color. Without one it silently inherits `body`'s
                    Telegram-theme-driven color, which is light in dark
                    theme and becomes invisible on this white background
                    (Stage 10H.2). The `dt` labels already had an explicit
                    color and were never affected. */}
                <dl className="space-y-1 text-sm min-w-0">
                  <div><dt className="inline text-slate-500">{t.projects.address}: </dt><dd className="inline font-medium text-slate-900">{selectedProject.address}, {selectedProject.postal_code} {selectedProject.city}</dd></div>
                  <div><dt className="inline text-slate-500">{t.projects.status}: </dt><dd className="inline font-medium text-slate-900">{statusLabel(selectedProject.status)}</dd></div>
                  <div><dt className="inline text-slate-500">{t.projects.client}: </dt><dd className="inline font-medium text-slate-900">{assignedClientName(selectedProject)}</dd></div>
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
                    className="min-h-11 px-3 text-xs rounded-lg bg-slate-50 border border-slate-200 text-slate-600 font-medium hover:bg-slate-100 transition"
                  >
                    <Ico>{selectedProject.is_archived ? '♻️' : '🗃️'}</Ico>{selectedProject.is_archived ? t.common.restore : t.common.archive}
                  </button>
                </div>
              </div>
              {selectedProject.description && <p className="text-sm text-slate-600 mt-3">{selectedProject.description}</p>}
            </article>

              <ProjectHub
                onOpenEstimates={() => {
                  setShowEstimates(true);
                  setSelectedEstimate(null);
                }}
                onOpenSection={(section) => {
                  setLegalSection(null);
    setDocumentsSection(null);
                  setObjectSection(section);
                }}
              />
              <PrepareOfflineButton projectId={selectedProject.id} />
            </div>
          )}

          {objectSection === 'rooms' && (
            <RoomList
              projectId={selectedProject.id}
              onOpenRoom={openRoom}
              onRoomChanged={() => {
                load();
                setSummaryToken((n) => n + 1);
              }}
            />
          )}

          {/* Stage 13F-PRE: the totals of the object, a screen of its own (the last tile of the hub). */}
          {objectSection === 'notes' && <ProjectNotes projectId={selectedProject.id} />}

          {objectSection === 'summary' && <ProjectSummaryCard projectId={selectedProject.id} refreshToken={summaryToken} />}

          {/* Stage 14E.5: photos of the whole object. */}
          {objectSection === 'photos' && <ObjectPhotos />}

          {/* Stage 15F: the technological card, the production plan, the photo report and the journal of the object — a list, each opened alone. */}
          {objectSection === 'documents' && documentsSection === null && <DocumentsMenu onOpen={setDocumentsSection} />}
          {objectSection === 'documents' && documentsSection !== null && (
            <ProjectDocuments
              projectId={selectedProject.id}
              part={documentsSection}
              onOpenInspection={(work) => void openRecommendationInspection(work)}
              onOpenEstimate={(estimateId) => void openCurrentEstimate(estimateId)}
            />
          )}

          {objectSection === 'legal' && legalSection === null && <LegalMenu onOpen={setLegalSection} />}

          {/* Stage 17E: the basis (law and norms) of the document of the open screen; nothing is shown when the knowledge base has none. */}
          {objectSection === 'legal' && legalSection !== null && LEGAL_BASIS[legalSection] && (
            <KnowledgeBasis targets={LEGAL_BASIS[legalSection]} name={`knowledge-basis-${legalSection}`} heading={t.knowledge.basis_document} />
          )}

          {/* Stage 16B.2: the persons of the object (who may accept the work and sign the protocols). */}
          {objectSection === 'legal' && legalSection === 'representatives' && <ProjectRepresentatives projectId={selectedProject.id} />}

          {/* Stage 16D.1: works of other contractors on the object (the register the production plan refers to). */}
          {objectSection === 'legal' && legalSection === 'adjacent' && <ProjectAdjacentWorks projectId={selectedProject.id} />}

          {/* Stage 16E.1: the questionnaire "compose the contract". */}
          {objectSection === 'legal' && legalSection === 'contract' && <ProjectContract projectId={selectedProject.id} />}

          {/* Stage 16F.3: the protocol of handing over the premises (the state of each room before the work). */}
          {objectSection === 'legal' && legalSection === 'handover' && <ProjectHandover projectId={selectedProject.id} />}

          {/* Stage 16G.2: the protocol of acceptance of concealed works (before the next layer covers them). */}
          {objectSection === 'legal' && legalSection === 'concealed' && <ProjectConcealedWorks projectId={selectedProject.id} />}

          {/* Stage 16H.3: the final or partial acceptance of the work (the result is derived from the works and the remarks). */}
          {objectSection === 'legal' && legalSection === 'acceptance' && <ProjectAcceptance projectId={selectedProject.id} />}

          {/* Stage 16I.2: the protocol of information and decisions of the customer (a recommendation given up or overruled). */}
          {objectSection === 'legal' && legalSection === 'decisions' && <ProjectDecisions projectId={selectedProject.id} />}

          {/* Stage 16I.4: the notice and the protocol of downtime on the customer's side. */}
          {objectSection === 'legal' && legalSection === 'downtime' && <ProjectDowntime projectId={selectedProject.id} />}
        </>
      )}

      {selectedProject && !selectedRoom && showEstimates && !selectedEstimate && (
        <>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-bold text-[var(--tg-theme-text-color)]">{t.estimates.title}</h2>
          </div>
          <EstimateList
            projectId={selectedProject.id}
            onOpenEstimate={(estimate) => {
              setSelectedEstimateGroupKey(null);
              setSelectedEstimate(estimate);
            }}
          />
        </>
      )}

      {selectedProject && !selectedRoom && showEstimates && selectedEstimate && (
        <EstimateShell
          estimate={selectedEstimate}
          onBack={() => setSelectedEstimate(null)}
          selectedGroupKey={selectedEstimateGroupKey}
          onGroupKeyChange={setSelectedEstimateGroupKey}
        />
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
                  className="min-h-10 text-xs px-3 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium hover:bg-blue-100 transition"
                >
                  <Ico>✏️</Ico>{t.common.edit}
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

                {/* Reveal (ościeże) summary */}
                {(selectedRoom.calculations?.window_reveal_total_length != null ||
                  selectedRoom.calculations?.door_reveal_total_length != null) && (
                  <div
                    aria-label="room-reveals-summary"
                    className="pt-2 border-t border-slate-100 space-y-1 text-[11px] text-slate-500"
                  >
                    <span className="block font-semibold text-slate-700">{t.reveals.summary_title}</span>
                    {selectedRoom.calculations?.window_reveal_total_length != null && (
                      <div className="flex justify-between">
                        <span>{t.reveals.summary_windows}</span>
                        <span>
                          <strong className="text-slate-700">{formatMetric(selectedRoom.calculations.window_reveal_total_length)} {t.common.unit_m}</strong>
                          {' / '}
                          <strong className="text-slate-700">{formatMetric(selectedRoom.calculations.window_reveal_total_area)} {t.common.unit_m2}</strong>
                        </span>
                      </div>
                    )}
                    {selectedRoom.calculations?.door_reveal_total_length != null && (
                      <div className="flex justify-between">
                        <span>{t.reveals.summary_doors}</span>
                        <span>
                          <strong className="text-slate-700">{formatMetric(selectedRoom.calculations.door_reveal_total_length)} {t.common.unit_m}</strong>
                          {' / '}
                          <strong className="text-slate-700">{formatMetric(selectedRoom.calculations.door_reveal_total_area)} {t.common.unit_m2}</strong>
                        </span>
                      </div>
                    )}
                    {selectedRoom.calculations?.reveal_total_length != null && (
                      <div className="flex justify-between font-medium text-slate-600">
                        <span>{t.reveals.summary_combined}</span>
                        <span>
                          <strong>{formatMetric(selectedRoom.calculations.reveal_total_length)} {t.common.unit_m}</strong>
                          {' / '}
                          <strong>{formatMetric(selectedRoom.calculations.reveal_total_area)} {t.common.unit_m2}</strong>
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* Stage 13F-PRE: which openings stand behind the figures above. */}
                {(selectedRoom.opening_groups ?? []).length > 0 && (
                  <div className="pt-2 border-t border-slate-100 text-[11px]">
                    <OpeningGroupList groups={selectedRoom.opening_groups ?? []} label="room-openings-summary" />
                  </div>
                )}
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

          {/* Stage 14E.6: every photo of the room — its surfaces and their openings included — for viewing and editing;
              photos are ADDED in the surface cards below. */}
          <article aria-label="room-photos" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{t.photos.section.room_title}</h3>
              <PhotoCardButton context="ROOM" targetId={selectedRoom.id} />
            </div>
            <PhotoCardPanel context="ROOM" targetId={selectedRoom.id} />
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
                  <DimensionInput
                    aria-label="room-edit-length"
                    placeholder="500"
                    value={roomForm.length}
                    onValueChange={(meters) => setRoomForm((cur) => ({ ...cur, length: meters }))}
                    className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t.rooms.width}</label>
                  <DimensionInput
                    aria-label="room-edit-width"
                    placeholder="400"
                    value={roomForm.width}
                    onValueChange={(meters) => setRoomForm((cur) => ({ ...cur, width: meters }))}
                    className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t.rooms.height}</label>
                  <DimensionInput
                    aria-label="room-edit-height"
                    placeholder="270"
                    value={roomForm.height}
                    onValueChange={(meters) => setRoomForm((cur) => ({ ...cur, height: meters }))}
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
                  <Ico>✖️</Ico>{t.common.cancel}
                </button>
                <button
                  type="submit"
                  disabled={savingRoom}
                  className="px-3 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition disabled:opacity-50"
                >
                  <Ico>💾</Ico>{savingRoom ? t.common.saving : t.common.save}
                </button>
              </div>
            </form>
          )}

          {/* Stage 13F-PRE FIX.2 (owner decision): no generic room-level
              inspection workflow. Inspections follow the inspected surface:
              WALL -> wall card Opcje, CEILING -> ceiling card Opcje. Historical
              room-level records stay in storage untouched (not deleted/migrated). */}
          <AreaSegmentList
            projectId={selectedProject.id}
            roomId={selectedRoom.id}
            roomName={selectedRoom.name}
            dimensionsKey={roomDimensionsKey}
            onMeasurementChanged={refreshSelectedRoom}
            onInspectPlane={(plane) => openInspectionList({ kind: 'plane', plane })}
          />

          <SurfaceList
            projectId={selectedProject.id}
            roomId={selectedRoom.id}
            roomName={selectedRoom.name}
            roomHeight={selectedRoom.height}
            dimensionsKey={roomDimensionsKey}
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
              <div className="space-y-3">
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
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    aria-label={`open-project-${project.id}`}
                    onClick={() => openProject(project)}
                    className="min-h-10 px-3 py-1 text-sm rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 transition"
                  >
                    <Ico>📂</Ico>{t.common.open}
                  </button>
                  <button
                    type="button"
                    aria-label={`notes-project-${project.id}`}
                    onClick={() => openProject(project, 'notes')}
                    className="min-h-10 px-3 py-1 text-sm rounded-xl bg-amber-50 text-amber-800 font-semibold hover:bg-amber-100 transition"
                  >
                    <Ico>📝</Ico>{t.notes.title}
                  </button>
                  <button
                    type="button"
                    aria-label={`edit-project-${project.id}`}
                    onClick={() => startEdit(project)}
                    className="min-h-10 px-3 py-1 text-sm rounded-xl bg-blue-50 text-blue-700 font-semibold hover:bg-blue-100 transition"
                  >
                    <Ico>✏️</Ico>{t.common.edit}
                  </button>
                  <button
                    type="button"
                    aria-label={`${project.is_archived ? 'restore' : 'archive'}-project-${project.id}`}
                    onClick={() => void changeArchiveState(project)}
                    className="min-h-10 px-3 py-1 text-sm rounded-xl bg-slate-50 border border-slate-200 text-slate-700 font-semibold hover:bg-slate-100 transition"
                  >
                    <Ico>{project.is_archived ? '♻️' : '🗃️'}</Ico>{project.is_archived ? t.common.restore : t.common.archive}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
    </ProjectPhotosProvider>
  );
}
