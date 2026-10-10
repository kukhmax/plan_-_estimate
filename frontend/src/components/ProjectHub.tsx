import { ReactNode, useEffect } from 'react';
import { photoKey, useProjectPhotos } from '../hooks/ProjectPhotosContext';
import { totalPhotoCount } from '../hooks/usePhotoCounts';
import { useI18n } from '../hooks/useI18n';
import { PhotoCardButton, PhotoCardPanel } from './PhotoCard';

// The screen of an object is a hub of large tiles; each tile opens one screen of its own (Stage 16K.3).
// The cards of the earlier stages live on those screens unchanged.

export type ObjectSection = 'rooms' | 'photos' | 'documents' | 'legal';

export type LegalSection =
  | 'representatives'
  | 'adjacent'
  | 'contract'
  | 'handover'
  | 'concealed'
  | 'acceptance'
  | 'decisions'
  | 'downtime';

interface TileProps {
  label: string;
  ariaLabel: string;
  onOpen: () => void;
  /** A small number on the right (photos). */
  count?: number;
  accent?: boolean;
}

function Tile({ label, ariaLabel, onOpen, count, accent = false }: TileProps) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onOpen}
      className={
        accent
          ? 'w-full min-h-14 bg-amber-500 border border-amber-600 rounded-2xl px-4 py-3 shadow-md flex items-center justify-between gap-3 text-left hover:bg-amber-400 active:bg-amber-600 transition'
          : 'w-full min-h-14 bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm flex items-center justify-between gap-3 text-left hover:bg-slate-50 transition'
      }
    >
      <span className={`font-bold text-sm break-words min-w-0 ${accent ? 'text-slate-950' : 'text-slate-900'}`}>{label}</span>
      <span className="flex items-center gap-2 shrink-0">
        {count !== undefined && (
          <span aria-label={`${ariaLabel}-count`} className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold">
            {count}
          </span>
        )}
        <span aria-hidden="true" className={`text-lg leading-none ${accent ? 'text-slate-950' : 'text-slate-400'}`}>›</span>
      </span>
    </button>
  );
}

interface ProjectHubProps {
  onOpenEstimates: () => void;
  onOpenSection: (section: ObjectSection) => void;
}

/** The tiles of an open object: the estimate first (it is what the contractor is paid by), then the work places. */
export function ProjectHub({ onOpenEstimates, onOpenSection }: ProjectHubProps) {
  const { t } = useI18n();
  const photos = useProjectPhotos();
  return (
    <nav aria-label="object-hub" className="grid grid-cols-1 gap-3">
      <Tile accent ariaLabel="open-estimates" label={t.estimates.title} onOpen={onOpenEstimates} />
      <Tile ariaLabel="object-tile-rooms" label={t.rooms.title} onOpen={() => onOpenSection('rooms')} />
      <Tile
        ariaLabel="object-tile-photos"
        label={t.photos.section.project_title}
        count={photos ? totalPhotoCount(photos.counts) : undefined}
        onOpen={() => onOpenSection('photos')}
      />
      <Tile ariaLabel="object-tile-documents" label={t.documents.title} onOpen={() => onOpenSection('documents')} />
      <Tile ariaLabel="object-tile-legal" label={t.objectHub.legal} onOpen={() => onOpenSection('legal')} />
    </nav>
  );
}

interface LegalMenuProps {
  onOpen: (section: LegalSection) => void;
}

/** "Umowa i protokoły": the persons, the other contractors, the contract and the protocols, each opened on its own. */
export function LegalMenu({ onOpen }: LegalMenuProps) {
  const { t } = useI18n();
  const groups: { title: string; items: { id: LegalSection; label: string }[] }[] = [
    {
      title: t.objectHub.group_parties,
      items: [
        { id: 'representatives', label: t.representatives.title },
        { id: 'adjacent', label: t.adjacentWorks.title },
      ],
    },
    { title: t.objectHub.group_contract, items: [{ id: 'contract', label: t.contract.title }] },
    {
      title: t.objectHub.group_protocols,
      items: [
        { id: 'handover', label: t.handover.title },
        { id: 'concealed', label: t.concealed.title },
        { id: 'acceptance', label: t.acceptance.title },
        { id: 'decisions', label: t.decisions.title },
        { id: 'downtime', label: t.downtime.title },
      ],
    },
  ];
  return (
    <div aria-label="legal-menu" className="space-y-4">
      {groups.map((group) => (
        <section key={group.title} aria-label={`legal-group-${group.items[0].id}`} className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--tg-theme-hint-color)]">{group.title}</h3>
          {group.items.map((item) => (
            <Tile key={item.id} ariaLabel={`legal-tile-${item.id}`} label={item.label} onOpen={() => onOpen(item.id)} />
          ))}
        </section>
      ))}
    </div>
  );
}

/** The photos of the whole object: the list is open at once, one tap fewer than before. */
export function ObjectPhotos(): ReactNode {
  const { t } = useI18n();
  const photos = useProjectPhotos();
  const key = photoKey('PROJECT');
  useEffect(() => {
    if (photos && !photos.isExpanded(key)) photos.toggle(key);
    // opened once, when the screen opens; a later tap on the button collapses it as usual
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photos?.projectId]);
  return (
    <article aria-label="project-photos" className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{t.photos.section.project_title}</h3>
        <PhotoCardButton context="PROJECT" />
      </div>
      <PhotoCardPanel context="PROJECT" />
    </article>
  );
}
