import { useEffect, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import {
  archiveInspection,
  fetchInspections,
  reopenInspection,
  restoreInspection,
} from '../api/inspections';
import { Inspection, InspectionTarget } from '../types/inspection';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';

export interface InspectionListProps {
  projectId: string;
  roomId: string;
  target: InspectionTarget;
  onStart: (target: InspectionTarget) => void;
  onOpen: (inspectionId: string) => void;
}

const SUBSTRATE_ORDER: SubstrateValue[] = [
  'CONCRETE',
  'GYPSUM_PLASTER',
  'CEMENT_LIME_PLASTER',
  'GYPSUM_BOARD',
  'PAINTED',
  'OTHER',
];

function substrateLabel(t: ReturnType<typeof useI18n>['t'], substrate: SubstrateValue): string {
  const key = `substrate_${substrate.toLowerCase()}` as keyof typeof t.inspections;
  return String(t.inspections[key] ?? substrate);
}

function qualityLabel(quality: QualityLevelValue | null): string {
  return quality ?? '—';
}

function targetLabel(
  t: ReturnType<typeof useI18n>['t'],
  target: InspectionTarget,
): string {
  if (target.kind === 'surface') {
    return target.surfaceName ?? t.inspections.inspect_wall;
  }
  if (target.kind === 'plane') {
    return target.plane === 'FLOOR'
      ? t.inspections.inspect_floor
      : t.inspections.inspect_ceiling;
  }
  return t.inspections.inspect_room;
}

function matchesTarget(inspection: Inspection, target: InspectionTarget): boolean {
  if (target.kind === 'surface') {
    return inspection.surface_id === target.surfaceId;
  }
  if (target.kind === 'plane') {
    return inspection.plane === target.plane;
  }
  return inspection.surface_id === null && inspection.plane === null;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString();
}

function InspectionCard({
  projectId,
  roomId,
  inspection,
  onOpen,
  onMutated,
}: {
  projectId: string;
  roomId: string;
  inspection: Inspection;
  onOpen: (inspectionId: string) => void;
  onMutated: () => void;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);

  const isCompleted = inspection.status === 'COMPLETED';

  async function handleReopen() {
    setBusy(true);
    try {
      await reopenInspection(projectId, roomId, inspection.id);
      onMutated();
    } finally {
      setBusy(false);
    }
  }

  async function handleArchive() {
    setBusy(true);
    try {
      await archiveInspection(projectId, roomId, inspection.id);
      onMutated();
    } finally {
      setBusy(false);
    }
  }

  async function handleRestore() {
    setBusy(true);
    try {
      await restoreInspection(projectId, roomId, inspection.id);
      onMutated();
    } finally {
      setBusy(false);
    }
  }

  const primaryAction = (
    <button
      type="button"
      aria-label={isCompleted ? t.inspections.view : t.inspections.open}
      className="min-h-11 flex-1 rounded-lg bg-blue-600 px-3 font-medium text-white"
      onClick={() => onOpen(inspection.id)}
    >
      {isCompleted ? t.inspections.view : t.inspections.open}
    </button>
  );

  const secondaryActions = (
    <>
      {isCompleted ? (
        <button
          type="button"
          aria-label={t.inspections.reopen}
          className="min-h-10 rounded-lg border border-blue-600 px-3 text-blue-700 disabled:opacity-50"
          disabled={busy}
          onClick={handleReopen}
        >
          {t.inspections.reopen}
        </button>
      ) : (
        <button
          type="button"
          aria-label={t.inspections.resume}
          className="min-h-10 rounded-lg border border-blue-600 px-3 text-blue-700"
          onClick={() => onOpen(inspection.id)}
        >
          {t.inspections.resume}
        </button>
      )}
      <button
        type="button"
        aria-label={inspection.is_archived ? t.inspections.restore : t.inspections.archive}
        className="min-h-10 rounded-lg border border-neutral-300 px-3 text-neutral-700 disabled:opacity-50"
        disabled={busy}
        onClick={inspection.is_archived ? handleRestore : handleArchive}
      >
        {inspection.is_archived ? t.inspections.restore : t.inspections.archive}
      </button>
    </>
  );

  return (
    <li className="rounded-lg border border-neutral-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm font-semibold text-neutral-900">
          {substrateLabel(t, inspection.substrate)}
        </p>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
            isCompleted
              ? 'bg-green-100 text-green-800'
              : 'bg-amber-100 text-amber-800'
          }`}
        >
          {isCompleted ? t.inspections.status_completed : t.inspections.status_draft}
        </span>
      </div>
      <p className="mt-1 text-xs text-neutral-600">
        {t.inspections.quality_target}: {qualityLabel(inspection.quality_target)}
        {isCompleted && inspection.completed_at
          ? ` · ${t.inspections.completed}: ${formatDate(inspection.completed_at)}`
          : ''}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {primaryAction}
        {secondaryActions}
      </div>
    </li>
  );
}

export function InspectionList({
  projectId,
  roomId,
  target,
  onStart,
  onOpen,
}: InspectionListProps) {
  const { t } = useI18n();
  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchInspections(projectId, roomId, showArchived);
      setInspections(result.items.filter((item) => matchesTarget(item, target)));
    } catch (err) {
      setError(err instanceof Error ? err.message : t.inspections.error_load);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, roomId, showArchived, target]);

  return (
    <section
      aria-label={t.inspections.title}
      className="flex flex-col gap-3 rounded-lg border border-neutral-200 bg-neutral-50 p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-neutral-900">
            {t.inspections.title}
          </h3>
          <p className="text-xs text-neutral-600">{targetLabel(t, target)}</p>
        </div>
        <button
          type="button"
          aria-label={t.inspections.start}
          className="min-h-11 shrink-0 rounded-lg bg-blue-600 px-4 font-medium text-white"
          onClick={() => onStart(target)}
        >
          {t.inspections.start}
        </button>
      </div>

      <label className="flex items-center gap-2 text-sm text-neutral-700">
        <input
          type="checkbox"
          checked={showArchived}
          onChange={(event) => setShowArchived(event.target.checked)}
        />
        {t.inspections.show_archived}
      </label>

      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-neutral-500">{t.inspections.loading}</p>
      ) : inspections.length === 0 ? (
        <p className="text-sm text-neutral-500">{t.inspections.empty}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {inspections.map((inspection) => (
            <InspectionCard
              key={inspection.id}
              projectId={projectId}
              roomId={roomId}
              inspection={inspection}
              onOpen={onOpen}
              onMutated={() => void load()}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

export { SUBSTRATE_ORDER };