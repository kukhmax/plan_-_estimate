import { ReactNode, useEffect, useState } from 'react';
import { fetchClientLink } from '../api/clientLink';
import { listEstimates } from '../api/estimates';
import { fetchRooms } from '../api/rooms';
import { formatDecimalMoney } from '../utils/format';
import { formatNoteTime } from '../utils/noteFormat';
import { photoKey, useProjectPhotos } from '../hooks/ProjectPhotosContext';
import { totalPhotoCount } from '../hooks/usePhotoCounts';
import { useI18n } from '../hooks/useI18n';
import { HubTile } from './HubTile';
import { PhotoCardButton, PhotoCardPanel } from './PhotoCard';

// The screen of an object is a hub of large tiles; each tile opens one screen of its own (Stage 16K.3).
// The cards of the earlier stages live on those screens unchanged.

export type ObjectSection = 'rooms' | 'photos' | 'documents' | 'legal' | 'payments' | 'materials' | 'summary' | 'notes' | 'client' | 'masters';
// 'notes' has no tile: the notes of an object are opened with the button of its card in the list of objects.

/** What the screen of documents lists: each piece of it is opened alone. */
export type DocumentsSection = 'measurements' | 'tech_card' | 'plan' | 'settlement' | 'payment_schedule' | 'installation_map' | 'photo_report' | 'journal';

const DOCUMENT_ICONS: Record<string, string> = { measurements: '📐', tech_card: '📋', plan: '🗓️', settlement: '🧾', payment_schedule: '📆', installation_map: '🧰', photo_report: '🖼️', journal: '📨' };
const LEGAL_ICONS: Record<string, string> = {
  representatives: '🤝',
  adjacent: '🔧',
  contract: '📜',
  handover: '🔑',
  concealed: '🧱',
  pressure: '💧',
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
  | 'pressure'
  | 'acceptance'
  | 'decisions'
  | 'downtime';

interface ProjectHubProps {
  onOpenEstimates: () => void;
  onOpenSection: (section: ObjectSection) => void;
  /** UX walk: with the object known the tiles say where it stands (rooms, the estimate, the client's link). */
  projectId?: string;
}

interface HubState {
  rooms: number | null;
  estimate: string | null;
  client: string | null;
}

/** The tiles of an open object: the rooms first (the work starts with measuring them; the owner's choice of 2026-10-19), then the estimate, then the other work places. */
export function ProjectHub({ onOpenEstimates, onOpenSection, projectId }: ProjectHubProps) {
  const { t, locale } = useI18n();
  const photos = useProjectPhotos();
  const [state, setState] = useState<HubState>({ rooms: null, estimate: null, client: null });

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    const words = t.objectHub;
    const statusWord = (status: string) =>
      ({ DRAFT: t.estimates.status_draft, FINAL: t.estimates.status_final, ACCEPTED: t.estimates.status_accepted, ARCHIVED: t.estimates.status_archived })[status] ?? status;
    // each line of the state is read on its own: a failed read only leaves its tile without the line (the tile itself works as before)
    void fetchRooms(projectId)
      .then((rooms) => !cancelled && setState((s) => ({ ...s, rooms: rooms.items.filter((room) => !room.is_archived).length })))
      .catch(() => undefined);
    void listEstimates(projectId)
      .then((list) => {
        const live = list.items.filter((estimate) => estimate.status !== 'ARCHIVED').sort((a, b) => b.version - a.version)[0];
        if (cancelled || !live) return;
        const amount = live.gross_total ?? live.total;
        const parts = [words.estimate_version.replace('{n}', String(live.version)), amount !== null ? `${formatDecimalMoney(amount)} ${live.currency}` : null, statusWord(live.status)];
        setState((s) => ({ ...s, estimate: parts.filter(Boolean).join(' · ') }));
      })
      .catch(() => undefined);
    void fetchClientLink(projectId)
      .then(({ link }) => {
        if (cancelled || !link || link.expired) return;
        setState((s) => ({
          ...s,
          client: link.last_viewed_at ? words.client_viewed.replace('{date}', formatNoteTime(link.last_viewed_at, locale)) : words.client_not_viewed,
        }));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, locale]);

  return (
    <nav aria-label="object-hub" className="grid grid-cols-1 gap-3">
      <HubTile
        tone="green"
        icon="🚪"
        ariaLabel="object-tile-rooms"
        label={t.rooms.title}
        detail={state.rooms === null ? null : state.rooms === 0 ? t.objectHub.rooms_none : t.objectHub.rooms_count.replace('{count}', String(state.rooms))}
        onOpen={() => onOpenSection('rooms')}
      />
      <HubTile accent icon="🧮" ariaLabel="open-estimates" label={t.estimates.title} detail={state.estimate} onOpen={onOpenEstimates} />
      <HubTile tone="sky" icon="🔗" ariaLabel="object-tile-client" label={t.client_link.title} detail={state.client} onOpen={() => onOpenSection('client')} />
      <HubTile tone="sky" icon="🔌" ariaLabel="object-tile-masters" label={t.trade_links.title} onOpen={() => onOpenSection('masters')} />
      <HubTile
        tone="sky"
        icon="📷"
        ariaLabel="object-tile-photos"
        label={t.photos.section.project_title}
        count={photos ? totalPhotoCount(photos.counts) : undefined}
        onOpen={() => onOpenSection('photos')}
      />
      <HubTile tone="pink" icon="📄" ariaLabel="object-tile-documents" label={t.documents.title} onOpen={() => onOpenSection('documents')} />
      <HubTile tone="slate" icon="⚖️" ariaLabel="object-tile-legal" label={t.objectHub.legal} onOpen={() => onOpenSection('legal')} />
      <HubTile tone="yellow" icon="💰" ariaLabel="object-tile-payments" label={t.payments.title} onOpen={() => onOpenSection('payments')} />
      <HubTile tone="green" icon="🧱" ariaLabel="object-tile-materials" label={t.materials.title} onOpen={() => onOpenSection('materials')} />
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
    { id: 'measurements', label: t.documents.kind_measurements },
    { id: 'tech_card', label: t.documents.kind_tech_card },
    { id: 'plan', label: t.documents.kind_production_plan },
    { id: 'settlement', label: t.documents.kind_settlement },
    { id: 'payment_schedule', label: t.documents.kind_payment_schedule },
    { id: 'installation_map', label: t.documents.kind_installation_map },
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
        { id: 'pressure', label: t.pressure.title },
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
    <article aria-label="project-photos" className="pe-card rounded-2xl p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 break-words text-sm font-semibold text-slate-900">{t.photos.section.project_title}</h3>
        <PhotoCardButton context="PROJECT" />
      </div>
      <PhotoCardPanel context="PROJECT" />
    </article>
  );
}
