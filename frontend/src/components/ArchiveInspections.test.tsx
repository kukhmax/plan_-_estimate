import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import { ArchiveScreen } from './ArchiveScreen';

vi.mock('../api/clients', () => ({ fetchClients: vi.fn(), restoreClient: vi.fn(), fetchClientDeletePreview: vi.fn(), deleteClient: vi.fn() }));
vi.mock('../api/projects', () => ({ fetchProjects: vi.fn(), restoreProject: vi.fn(), fetchProjectPurgePreview: vi.fn(), purgeProject: vi.fn() }));
vi.mock('../api/archiveStructure', () => ({ fetchArchivedStructure: vi.fn() }));
vi.mock('../api/archiveInspections', () => ({ fetchArchivedInspections: vi.fn() }));
vi.mock('../api/inspections', () => ({ restoreInspection: vi.fn() }));
vi.mock('../api/rooms', () => ({ restoreRoom: vi.fn() }));
vi.mock('../api/surfaces', () => ({ restoreSurface: vi.fn() }));
vi.mock('../api/structurePurge', () => ({
  fetchRoomPurgePreview: vi.fn(),
  purgeRoom: vi.fn(),
  fetchSurfacePurgePreview: vi.fn(),
  purgeSurface: vi.fn(),
  fetchInspectionPurgePreview: vi.fn(),
  purgeInspection: vi.fn(),
}));
vi.mock('../api/photos', async () => ({
  ...(await vi.importActual<typeof import('../api/photos')>('../api/photos')),
  fetchPhotoArchive: vi.fn(),
}));
import { ArchivedInspectionItem, fetchArchivedInspections } from '../api/archiveInspections';
import { fetchArchivedStructure } from '../api/archiveStructure';
import { fetchClients } from '../api/clients';
import { restoreInspection } from '../api/inspections';
import { fetchPhotoArchive } from '../api/photos';
import { fetchProjects } from '../api/projects';
import { fetchInspectionPurgePreview, purgeInspection, StructurePurgePreview } from '../api/structurePurge';

const P1 = '11111111-1111-4111-8111-111111111111';
const R1 = '22222222-2222-4222-8222-222222222222';

const item = (id: string, over: Partial<ArchivedInspectionItem> = {}): ArchivedInspectionItem => ({
  id, status: 'COMPLETED', substrate: 'CONCRETE', quality_target: null, plane: null, created_at: '2026-10-12T09:30:00Z', completed_at: '2026-10-12T10:00:00Z',
  room_id: R1, room_name: 'Salon', surface_id: null, surface_name: null, surface_type: null, project_id: P1, project_name: 'Mieszkanie Mokotów', ...over,
});

const LIST = [
  item('i-room'),
  item('i-wall', { surface_id: 's1', surface_name: 'Ściana 1', surface_type: 'WALL', substrate: 'GYPSUM_PLASTER', status: 'DRAFT' }),
  item('i-floor', { plane: 'FLOOR', substrate: 'PAINTED' }),
];

const preview = (over: Partial<StructurePurgePreview> = {}): StructurePurgePreview => ({
  kind: 'INSPECTION', target_id: 'i-room', name: 'CONCRETE', archived: true, can_purge: true, surfaces: 0, openings: 0, inspections: 1, photos: 3, photo_files: 3,
  bytes: 2 * 1024 * 1024, annotations: 2, estimate_lines: 0, answers: 12, findings: 4, risks: 2, recommendations: 3, may_be_in_backups: true, blockers: [], ...over,
});

function renderScreen() {
  return render(<I18nProvider><ArchiveScreen /></I18nProvider>);
}

const openTab = async () => {
  fireEvent.click(await screen.findByLabelText('archive-tab-inspections'));
};

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(fetchClients).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(fetchProjects).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(fetchArchivedStructure).mockResolvedValue({ rooms: [], surfaces: [], rooms_total: 0, surfaces_total: 0 });
  vi.mocked(fetchArchivedInspections).mockResolvedValue({ items: LIST, total: 3 });
  vi.mocked(fetchPhotoArchive).mockResolvedValue({ items: [], archived_total: 0, trashed_total: 0, urls_expire_at: null });
});

describe('ArchiveScreen: archived inspections (archive cleanup AC-7)', () => {
  it('has the tab with the number the server counted', async () => {
    renderScreen();
    await waitFor(() => expect(screen.getByLabelText('archive-count-inspections')).toHaveTextContent('(3)'));
    expect(screen.getByLabelText('archive-tab-inspections')).toHaveTextContent('Badania');
  });

  it('lists them by the place they were made at, with the substrate, the state, and the object and room', async () => {
    renderScreen();
    await openTab();
    const list = await screen.findByLabelText('archive-inspections-list');
    const wall = within(within(list).getByLabelText('archived-inspection-i-wall'));
    expect(wall.getByText('Ściana 1')).toBeInTheDocument();
    expect(wall.getByText(/Podłoże: Tynk gipsowy · Szkic/)).toBeInTheDocument();
    expect(wall.getByText('Obiekt: Mieszkanie Mokotów → pomieszczenie: Salon')).toBeInTheDocument();
    const room = within(within(list).getByLabelText('archived-inspection-i-room'));
    expect(room.getByText('Badanie pomieszczenia')).toBeInTheDocument();
    expect(room.getByText(/Podłoże: Beton · Zakończone/)).toBeInTheDocument();
    expect(within(within(list).getByLabelText('archived-inspection-i-floor')).getByText('Podłoga')).toBeInTheDocument();
  });

  it('says so when there are none', async () => {
    vi.mocked(fetchArchivedInspections).mockResolvedValue({ items: [], total: 0 });
    renderScreen();
    await openTab();
    expect(await screen.findByLabelText('archive-empty-inspections')).toHaveTextContent('Brak zarchiwizowanych badań.');
  });

  it('says how many are shown of the whole when the list is cut', async () => {
    vi.mocked(fetchArchivedInspections).mockResolvedValue({ items: LIST, total: 250 });
    renderScreen();
    await openTab();
    expect(await screen.findByText('Pokazano pierwsze 3 z 250.')).toBeInTheDocument();
  });

  it('restore puts the inspection back: it leaves the list, the number goes down', async () => {
    vi.mocked(restoreInspection).mockResolvedValue({} as never);
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('restore-inspection-i-wall'));
    await waitFor(() => expect(restoreInspection).toHaveBeenCalledWith(P1, R1, 'i-wall'));
    await waitFor(() => expect(screen.queryByLabelText('archived-inspection-i-wall')).toBeNull());
    expect(screen.getByLabelText('archived-inspection-i-room')).toBeInTheDocument();
    expect(screen.getByLabelText('archive-count-inspections')).toHaveTextContent('(2)');
    expect(screen.getByRole('status')).toHaveTextContent('Badanie przywrócone.');
  });

  it('a restore that fails keeps the row and tells so', async () => {
    vi.mocked(restoreInspection).mockRejectedValue(new ApiError('boom', 500));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('restore-inspection-i-room'));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByLabelText('archived-inspection-i-room')).toBeInTheDocument();
  });

  it('a failing list of inspections does not hide the rest and can be read again', async () => {
    vi.mocked(fetchArchivedInspections).mockRejectedValueOnce(new Error('down'));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('archive-retry'));
    expect(await screen.findByLabelText('archive-inspections-list')).toBeInTheDocument();
    // the other tabs were not touched by it
    fireEvent.click(screen.getByLabelText('archive-tab-rooms'));
    expect(await screen.findByLabelText('archive-empty-rooms')).toBeInTheDocument();
  });
});

describe('ArchiveScreen: deleting an archived inspection for good (archive cleanup AC-7)', () => {
  it('the server counts what goes, the deletion waits for the tick, then the inspection leaves the list and the photos are read again', async () => {
    vi.mocked(fetchInspectionPurgePreview).mockResolvedValue(preview());
    vi.mocked(purgeInspection).mockResolvedValue({ purged: true, photo_files: 3, storage_pending: 0 });
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-inspection-i-wall'));
    const lines = await screen.findByLabelText('structure-delete-lines');
    expect(fetchInspectionPurgePreview).toHaveBeenCalledWith(P1, R1, 'i-wall');
    expect(screen.getByText(/Z badania „Ściana 1” zostanie usunięte na zawsze/)).toBeInTheDocument();
    for (const expected of ['Odpowiedzi: 12', 'Ustalenia: 4', 'Ryzyka: 2', 'Zalecane prace: 3', 'Zdjęcia: 3; pliki w magazynie: 3 (2.1 MB)', 'Znaczniki na zdjęciach: 2']) {
      expect(within(lines).getByText(expected, { exact: false })).toBeInTheDocument();
    }
    expect(within(lines).queryByText(/Badania: /)).toBeNull(); // the inspection itself is not counted as a part of itself
    const confirm = screen.getByLabelText('structure-delete-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByLabelText('structure-delete-understood'));
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(purgeInspection).toHaveBeenCalledWith(P1, R1, 'i-wall'));
    await waitFor(() => expect(screen.queryByLabelText('archived-inspection-i-wall')).toBeNull());
    expect(screen.getByLabelText('archive-count-inspections')).toHaveTextContent('(2)');
    expect(screen.getByRole('status')).toHaveTextContent('Badanie usunięte.');
    await waitFor(() => expect(vi.mocked(fetchPhotoArchive).mock.calls.length).toBeGreaterThan(1));
  });

  it('an inspection with nothing under it says so', async () => {
    vi.mocked(fetchInspectionPurgePreview).mockResolvedValue(preview({ answers: 0, findings: 0, risks: 0, recommendations: 0, photos: 0, photo_files: 0, bytes: 0, annotations: 0, may_be_in_backups: false }));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-inspection-i-room'));
    expect(await screen.findByText('Nie ma tu nic więcej: ani odpowiedzi, ani ustaleń, ani zdjęć.')).toBeInTheDocument();
    expect(screen.queryByText(/osobny krok właściciela/)).toBeNull();
  });

  it('a protocol that is not archived holds it: the reason is told, no tick, no confirm button', async () => {
    vi.mocked(fetchInspectionPurgePreview).mockResolvedValue(preview({ can_purge: false, blockers: [{ kind: 'CONCEALED_WORKS', protocol_id: 'c', status: 'DRAFT' }] }));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-inspection-i-room'));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('protokół robót zanikających');
    expect(screen.queryByLabelText('structure-delete-confirm')).toBeNull();
    expect(screen.queryByLabelText('structure-delete-understood')).toBeNull();
    expect(purgeInspection).not.toHaveBeenCalled();
  });

  it('"Anuluj" deletes nothing', async () => {
    vi.mocked(fetchInspectionPurgePreview).mockResolvedValue(preview());
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-inspection-i-room'));
    await screen.findByLabelText('structure-delete-lines');
    fireEvent.click(screen.getByLabelText('structure-delete-cancel'));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(purgeInspection).not.toHaveBeenCalled();
    expect(screen.getByLabelText('archived-inspection-i-room')).toBeInTheDocument();
  });

  it('a change during the deletion keeps the row and asks to try again', async () => {
    vi.mocked(fetchInspectionPurgePreview).mockResolvedValue(preview());
    vi.mocked(purgeInspection).mockRejectedValue(new ApiError('conflict', 409, 'STRUCTURE_PURGE_CONFLICT'));
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-inspection-i-room'));
    await screen.findByLabelText('structure-delete-lines');
    fireEvent.click(screen.getByLabelText('structure-delete-understood'));
    fireEvent.click(screen.getByLabelText('structure-delete-confirm'));
    expect(await screen.findByText(/Zmieniło się w trakcie usuwania/)).toBeInTheDocument();
    expect(screen.getByLabelText('archived-inspection-i-room')).toBeInTheDocument();
  });

  it('the files still in the storage are said after the deletion', async () => {
    vi.mocked(fetchInspectionPurgePreview).mockResolvedValue(preview());
    vi.mocked(purgeInspection).mockResolvedValue({ purged: true, photo_files: 3, storage_pending: 3 });
    renderScreen();
    await openTab();
    fireEvent.click(await screen.findByLabelText('delete-inspection-i-room'));
    await screen.findByLabelText('structure-delete-lines');
    fireEvent.click(screen.getByLabelText('structure-delete-understood'));
    fireEvent.click(screen.getByLabelText('structure-delete-confirm'));
    expect(await screen.findByRole('status')).toHaveTextContent('Pliki zdjęć w magazynie zostaną usunięte przy ponowieniu.');
  });

  it('the Russian texts of the tab and of the deletion', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(fetchInspectionPurgePreview).mockResolvedValue(preview());
    renderScreen();
    await openTab();
    expect(screen.getByLabelText('archive-tab-inspections')).toHaveTextContent('Обследования');
    const wall = within(await screen.findByLabelText('archived-inspection-i-wall'));
    expect(wall.getByText(/Основание: Гипсовая штукатурка · Черновик/)).toBeInTheDocument();
    expect(wall.getByText('Объект: Mieszkanie Mokotów → помещение: Salon')).toBeInTheDocument();
    expect(within(screen.getByLabelText('archived-inspection-i-room')).getByText('Обследование помещения')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('delete-inspection-i-wall'));
    expect(await screen.findByText(/Из обследования «Стена 1» будет удалено навсегда/)).toBeInTheDocument();
    for (const expected of ['Ответы: 12', 'Установленные факты: 4', 'Риски: 2', 'Рекомендуемые работы: 3']) {
      expect(screen.getByText(expected, { exact: false })).toBeInTheDocument();
    }
  });
});
