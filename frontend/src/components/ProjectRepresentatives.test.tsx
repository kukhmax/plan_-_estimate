import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/representatives';
import { I18nProvider } from '../hooks/useI18n';
import type { ProjectRepresentative } from '../types/representative';
import { ProjectRepresentatives } from './ProjectRepresentatives';

vi.mock('../api/representatives', () => ({
  fetchRepresentatives: vi.fn(),
  createRepresentative: vi.fn(),
  updateRepresentative: vi.fn(),
  archiveRepresentative: vi.fn(),
  restoreRepresentative: vi.fn(),
}));

function person(over: Partial<ProjectRepresentative> = {}): ProjectRepresentative {
  return {
    id: 'r1', project_id: 'p1', side: 'SUPERVISION', name: 'Piotr Wiśniewski', role_title: 'Inspektor nadzoru', phone: '+48 600 100 200',
    email: 'piotr@example.pl', may_accept_and_sign: true, is_archived: false, created_at: '2026-10-09T10:00:00Z', updated_at: '2026-10-09T10:00:00Z', ...over,
  };
}

function list(...items: ProjectRepresentative[]) {
  return { items, total: items.length };
}

function renderCard() {
  return render(<I18nProvider><ProjectRepresentatives projectId="p1" /></I18nProvider>);
}

async function openAddForm() {
  fireEvent.click(await screen.findByLabelText('add-representative'));
  return screen.getByLabelText('representative-form');
}

describe('ProjectRepresentatives (Stage 16B.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchRepresentatives).mockResolvedValue(list());
  });

  it('loads the persons of the object and says when there are none', async () => {
    renderCard();
    expect(await screen.findByText('Nie dodano jeszcze żadnej osoby.')).toBeInTheDocument();
    expect(api.fetchRepresentatives).toHaveBeenCalledWith('p1', false);
    expect(screen.getByLabelText('add-representative').className).toContain('min-h-11');
  });

  it('shows a person with the side, the role, the mark "may accept and sign", a tel: link and the e-mail', async () => {
    vi.mocked(api.fetchRepresentatives).mockResolvedValue(list(person()));
    renderCard();
    const row = await screen.findByLabelText('representative-r1');
    expect(within(row).getByText('Piotr Wiśniewski')).toBeInTheDocument();
    expect(row).toHaveTextContent('Nadzór (inspektor, kierownik budowy) · Inspektor nadzoru');
    expect(within(row).getByText('Odbiera prace i podpisuje protokoły')).toBeInTheDocument();
    expect(within(row).getByLabelText('call-r1')).toHaveAttribute('href', 'tel:+48600100200');
    expect(row).toHaveTextContent('piotr@example.pl');
  });

  it('does not mark a person who may not sign', async () => {
    vi.mocked(api.fetchRepresentatives).mockResolvedValue(list(person({ may_accept_and_sign: false, phone: null, email: null, role_title: null })));
    renderCard();
    const row = await screen.findByLabelText('representative-r1');
    expect(within(row).queryByText('Odbiera prace i podpisuje protokoły')).toBeNull();
    expect(within(row).queryByLabelText('call-r1')).toBeNull();
  });

  it('adds a person: the four sides are offered, only what is filled in is sent, and the list is read again', async () => {
    vi.mocked(api.createRepresentative).mockResolvedValue(person());
    renderCard();
    const form = await openAddForm();
    const sides = within(form).getByLabelText('representative-side') as HTMLSelectElement;
    expect([...sides.options].map((o) => o.value)).toEqual(['CUSTOMER', 'CUSTOMER_REPRESENTATIVE', 'SUPERVISION', 'CONTRACTOR']);
    fireEvent.change(sides, { target: { value: 'SUPERVISION' } });
    fireEvent.change(within(form).getByLabelText('representative-name'), { target: { value: '  Piotr Wiśniewski ' } });
    fireEvent.click(within(form).getByLabelText('representative-may-sign'));
    await act(async () => { fireEvent.submit(form); });
    expect(api.createRepresentative).toHaveBeenCalledWith('p1', {
      side: 'SUPERVISION', name: 'Piotr Wiśniewski', role_title: undefined, phone: undefined, email: undefined, may_accept_and_sign: true,
    });
    await waitFor(() => expect(api.fetchRepresentatives).toHaveBeenCalledTimes(2));
    expect(screen.queryByLabelText('representative-form')).toBeNull();
  });

  it('refuses an empty name, a short phone and a wrong e-mail on the phone, before the server', async () => {
    renderCard();
    const form = await openAddForm();
    await act(async () => { fireEvent.submit(form); });
    expect(await screen.findByText('Podaj imię i nazwisko')).toBeInTheDocument();
    fireEvent.change(within(form).getByLabelText('representative-name'), { target: { value: 'Anna' } });
    fireEvent.change(within(form).getByLabelText('representative-phone'), { target: { value: '12-34' } });
    await act(async () => { fireEvent.submit(form); });
    expect(await screen.findByText(/Telefon: co najmniej 7 cyfr/)).toBeInTheDocument();
    fireEvent.change(within(form).getByLabelText('representative-phone'), { target: { value: '600 100 200' } });
    fireEvent.change(within(form).getByLabelText('representative-email'), { target: { value: 'bad' } });
    await act(async () => { fireEvent.submit(form); });
    expect(await screen.findByText(/E-mail: np\./)).toBeInTheDocument();
    expect(api.createRepresentative).not.toHaveBeenCalled();
  });

  it('shows the server message when saving fails and keeps the form', async () => {
    vi.mocked(api.createRepresentative).mockRejectedValue(new Error('email must look like name@example.pl'));
    renderCard();
    const form = await openAddForm();
    fireEvent.change(within(form).getByLabelText('representative-name'), { target: { value: 'Anna' } });
    await act(async () => { fireEvent.submit(form); });
    expect(await screen.findByLabelText('representative-error')).toHaveTextContent('email must look like name@example.pl');
    expect(screen.getByLabelText('representative-form')).toBeInTheDocument();
  });

  it('edits a person: the form is filled in and an emptied optional field is sent as null', async () => {
    vi.mocked(api.fetchRepresentatives).mockResolvedValue(list(person()));
    vi.mocked(api.updateRepresentative).mockResolvedValue(person());
    renderCard();
    fireEvent.click(await screen.findByLabelText('edit-representative-r1'));
    const form = screen.getByLabelText('representative-form');
    expect(within(form).getByLabelText('representative-name')).toHaveValue('Piotr Wiśniewski');
    expect((within(form).getByLabelText('representative-may-sign') as HTMLInputElement).checked).toBe(true);
    fireEvent.change(within(form).getByLabelText('representative-phone'), { target: { value: '' } });
    fireEvent.click(within(form).getByLabelText('representative-may-sign'));
    await act(async () => { fireEvent.submit(form); });
    expect(api.updateRepresentative).toHaveBeenCalledWith('p1', 'r1', {
      side: 'SUPERVISION', name: 'Piotr Wiśniewski', role_title: 'Inspektor nadzoru', phone: null, email: 'piotr@example.pl', may_accept_and_sign: false,
    });
  });

  it('archives a person, shows the archived ones on request and restores them', async () => {
    vi.mocked(api.fetchRepresentatives).mockResolvedValueOnce(list(person())).mockResolvedValue(list());
    vi.mocked(api.archiveRepresentative).mockResolvedValue(person({ is_archived: true }));
    renderCard();
    const archiveButton = await screen.findByLabelText('archive-representative-r1');
    await act(async () => { fireEvent.click(archiveButton); });
    expect(api.archiveRepresentative).toHaveBeenCalledWith('p1', 'r1');
    await waitFor(() => expect(screen.queryByLabelText('representative-r1')).toBeNull());
    vi.mocked(api.fetchRepresentatives).mockResolvedValue(list(person({ is_archived: true })));
    fireEvent.click(screen.getByLabelText('show-archived-representatives'));
    await waitFor(() => expect(api.fetchRepresentatives).toHaveBeenLastCalledWith('p1', true));
    const row = await screen.findByLabelText('representative-r1');
    expect(within(row).getByText('Zarchiwizowana')).toBeInTheDocument();
    expect(within(row).queryByLabelText('edit-representative-r1')).toBeNull();
    vi.mocked(api.restoreRepresentative).mockResolvedValue(person());
    await act(async () => { fireEvent.click(within(row).getByLabelText('restore-representative-r1')); });
    expect(api.restoreRepresentative).toHaveBeenCalledWith('p1', 'r1');
  });

  it('says when the list cannot be loaded and offers to try again', async () => {
    vi.mocked(api.fetchRepresentatives).mockRejectedValueOnce(new Error('network')).mockResolvedValue(list(person()));
    renderCard();
    expect(await screen.findByText('Nie udało się wczytać osób.')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Spróbuj ponownie'));
    expect(await screen.findByLabelText('representative-r1')).toBeInTheDocument();
  });

  it('is in Russian, with touch-sized controls and a phone keyboard for the phone', async () => {
    localStorage.setItem('locale', 'ru');
    vi.mocked(api.fetchRepresentatives).mockResolvedValue(list(person()));
    renderCard();
    expect(await screen.findByText('Лица объекта')).toBeInTheDocument();
    const row = screen.getByLabelText('representative-r1');
    expect(row).toHaveTextContent('Надзор (инспектор, руководитель строительства) · Inspektor nadzoru');
    expect(within(row).getByText('Принимает работы и подписывает протоколы')).toBeInTheDocument();
    for (const name of ['edit-representative-r1', 'archive-representative-r1']) expect(within(row).getByLabelText(name).className).toContain('min-h-11');
    fireEvent.click(screen.getByLabelText('add-representative'));
    const form = screen.getByLabelText('representative-form');
    expect(within(form).getByLabelText('representative-phone')).toHaveAttribute('inputmode', 'tel');
    expect(within(form).getByLabelText('representative-email')).toHaveAttribute('inputmode', 'email');
    expect(within(form).getByLabelText('representative-name')).toHaveAttribute('placeholder', 'Имя и фамилия');
    for (const control of [...within(form).getAllByRole('button'), ...within(form).getAllByRole('textbox'), within(form).getByRole('combobox')]) {
      expect(control.className).toContain('min-h-11');
    }
  });
});
