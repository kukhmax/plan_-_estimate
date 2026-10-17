import { ReactNode, useEffect } from 'react';
import { photoKey, useProjectPhotos } from '../hooks/ProjectPhotosContext';
import { totalPhotoCount } from '../hooks/usePhotoCounts';
import { useI18n } from '../hooks/useI18n';
import { HubTile } from './HubTile';
import { PhotoCardButton, PhotoCardPanel } from './PhotoCard';

// The screen of an object is a hub of large tiles; each tile opens one screen of its own (Stage 16K.3).
// The cards of the earlier stages live on those screens unchanged.

export type ObjectSection = 'rooms' | 'photos' | 'documents' | 'legal' | 'payments' | 'summary' | 'notes';
// 'notes' has no tile: the notes of an object are opened with the button of its card in the list of objects.

/** What the screen of documents lists: each piece of it is opened alone. */
export type DocumentsSection = 'tech_card' | 'plan' | 'photo_report' | 'journal';

const DOCUMENT_ICONS: Record<string, string> = { tech_card: '📋', plan: '🗓️', photo_report: '🖼️', journal: '📨' };
const LEGAL_ICONS: Record<string, string> = {
  representatives: '🤝',
  adjacent: '🔧',
  contract: '📜',
  handover: '🔑',
  concealed: '🧱',
  acceptance: '✅',
  decisions: '🖊️',
  downtime: '⏸️',
};

export type LegalSection =
  | 'representatives'
  | 'adjacent'
  | 'contract'
  | 'handover'
  | 'concealed'
  | 'acceptance'
  | 'decisions'
  | 'downtime';

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
      <HubTile accent icon="🧮" ariaLabel="open-estimates" label={t.estimates.title} onOpen={onOpenEstimates} />
      <HubTile icon="🚪" ariaLabel="object-tile-rooms" label={t.rooms.title} onOpen={() => onOpenSection('rooms')} />
      <HubTile
        icon="📷"
        ariaLabel="object-tile-photos"
        label={t.photos.section.project_title}
        count={photos ? totalPhotoCount(photos.counts) : undefined}
        onOpen={() => onOpenSection('photos')}
      />
      <HubTile icon="📄" ariaLabel="object-tile-documents" label={t.documents.title} onOpen={() => onOpenSection('documents')} />
      <HubTile icon="⚖️" ariaLabel="object-tile-legal" label={t.objectHub.legal} onOpen={() => onOpenSection('legal')} />
      <HubTile icon="💰" ariaLabel="object-tile-payments" label={t.payments.title} onOpen={() => onOpenSection('payments')} />
      <HubTile icon="📊" ariaLabel="object-tile-summary" label={t.object_summary.title} onOpen={() => onOpenSection('summary')} />
    </nav>
  );
}

interface DocumentsMenuProps {
  onOpen: (section: DocumentsSection) => void;
}

/** "PDF-dokumenty": the technological card, the production plan, the photo report and what was sent for this object. */
export function DocumentsMenu({ onOpen }: DocumentsMenuProps) {
  const { t } = useI18n();
  const rows: { id: DocumentsSection; label: string }[] = [
    { id: 'tech_card', label: t.documents.kind_tech_card },
    { id: 'plan', label: t.documents.kind_production_plan },
    { id: 'photo_report', label: t.documents.photo_report },
    { id: 'journal', label: t.documents.journal_title },
  ];
  return (
    <nav aria-label="documents-menu" className="grid grid-cols-1 gap-3">
      {rows.map((row) => (
        <HubTile key={row.id} icon={DOCUMENT_ICONS[row.id]} ariaLabel={`docs-tile-${row.id}`} label={row.label} onOpen={() => onOpen(row.id)} />
      ))}
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
            <HubTile key={item.id} icon={LEGAL_ICONS[item.id]} ariaLabel={`legal-tile-${item.id}`} label={item.label} onOpen={() => onOpen(item.id)} />
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
