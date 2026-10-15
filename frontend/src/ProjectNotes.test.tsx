import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as notesApi from './api/projectNotes';
import { ApiError } from './api/http';
import { ProjectNotes } from './components/ProjectNotes';
import { I18nProvider } from './hooks/useI18n';
import type { ProjectNote } from './types/projectNote';
import { formatNoteTime } from './utils/noteFormat';

vi.mock('./api/projectNotes', () => ({
  fetchProjectNotes: vi.fn(),
  createProjectNote: vi.fn(),
  updateProjectNote: vi.fn(),
  deleteProjectNote: vi.fn(),
}));

const projectId = '11111111-1111-1111-1111-111111111111';
const note = (id: string, body: string, created = '2026-10-15T12:30:00Z', updated = created): ProjectNote => ({
  id, project_id: projectId, body, created_at: created, updated_at: updated,
});
const NEWER = note('n2', 'Zamówić gładź', '2026-10-15T14:05:00Z');
const OLDER = note('n1', 'Klient prosi o inny kolor', '2026-10-14T08:00:00Z');

function renderNotes() {
  return render(<I18nProvider><ProjectNotes projectId={projectId} /></I18nProvider>);
}

describe('ProjectNotes (Stage 18)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(notesApi.fetchProjectNotes).mockResolvedValue({ items: [NEWER, OLDER], total: 2 });
  });

  it('lists the notes in the order given with the day and the time each was written', async () => {
    renderNotes();

    const list = await screen.findByLabelText('notes-list');
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Zamówić gładź');
    expect(items[1]).toHaveTextContent('Klient prosi o inny kolor');
    expect(screen.getByLabelText('note-time-n2').textContent).toBe(formatNoteTime(NEWER.created_at, 'pl'));
    expect(screen.getByLabelText('note-time-n2').textContent).toMatch(/15\.10\.2026.*\d{2}:\d{2}/);
    expect(screen.getByLabelText('note-time-n1').textContent).toMatch(/14\.10\.2026/);
    expect(notesApi.fetchProjectNotes).toHaveBeenCalledWith(projectId);
  });

  it('shows an empty state and nothing else when there are no notes', async () => {
    vi.mocked(notesApi.fetchProjectNotes).mockResolvedValue({ items: [], total: 0 });
    renderNotes();

    expect(await screen.findByLabelText('notes-empty')).toHaveTextContent('Brak notatek');
    expect(screen.queryByLabelText('notes-list')).toBeNull();
  });

  it('writes a note: the button is off while the field is blank, the new note goes first and the field is cleared', async () => {
    const created = note('n3', 'Nowa myśl', '2026-10-15T15:00:00Z');
    vi.mocked(notesApi.createProjectNote).mockResolvedValue(created);
    renderNotes();
    await screen.findByLabelText('notes-list');
    const add = screen.getByLabelText('note-add');
    expect(add).toBeDisabled();
    fireEvent.change(screen.getByLabelText('note-input'), { target: { value: '   ' } });
    expect(add).toBeDisabled();

    fireEvent.change(screen.getByLabelText('note-input'), { target: { value: 'Nowa myśl' } });
    expect(add).toBeEnabled();
    fireEvent.click(add);

    await waitFor(() => expect(notesApi.createProjectNote).toHaveBeenCalledWith(projectId, 'Nowa myśl'));
    await waitFor(() => expect(within(screen.getByLabelText('notes-list')).getAllByRole('listitem')[0]).toHaveTextContent('Nowa myśl'));
    expect(screen.getByLabelText('note-input')).toHaveValue('');
    expect(screen.getByRole('status')).toHaveTextContent('Notatka zapisana.');
  });

  it('keeps the words when writing fails and says why', async () => {
    vi.mocked(notesApi.createProjectNote).mockRejectedValue(new ApiError('A note cannot be empty', 422, 'NOTE_INVALID'));
    renderNotes();
    await screen.findByLabelText('notes-list');
    fireEvent.change(screen.getByLabelText('note-input'), { target: { value: 'Ważne' } });
    fireEvent.click(screen.getByLabelText('note-add'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Notatka jest pusta lub zbyt długa.');
    expect(screen.getByLabelText('note-input')).toHaveValue('Ważne');
    expect(within(screen.getByLabelText('notes-list')).getAllByRole('listitem')).toHaveLength(2);
  });

  it('changes a note in place and shows when it was changed', async () => {
    const changed = note('n2', 'Zamówić gładź i grunt', NEWER.created_at, '2026-10-16T09:00:00Z');
    vi.mocked(notesApi.updateProjectNote).mockResolvedValue(changed);
    renderNotes();
    await screen.findByLabelText('notes-list');

    fireEvent.click(screen.getByLabelText('note-edit-n2'));
    const input = screen.getByLabelText('note-edit-input-n2');
    expect(input).toHaveValue('Zamówić gładź');
    fireEvent.change(input, { target: { value: 'Zamówić gładź i grunt' } });
    fireEvent.click(screen.getByLabelText('note-edit-save-n2'));

    await waitFor(() => expect(notesApi.updateProjectNote).toHaveBeenCalledWith(projectId, 'n2', 'Zamówić gładź i grunt'));
    expect(await screen.findByLabelText('note-body-n2')).toHaveTextContent('Zamówić gładź i grunt');
    expect(screen.getByLabelText('note-time-n2')).toHaveTextContent('zmieniono');
    expect(screen.getByLabelText('note-time-n1')).not.toHaveTextContent('zmieniono');
    expect(screen.queryByLabelText('note-edit-input-n2')).toBeNull();
  });

  it('cancelling an edit leaves the note as it was, and a blank edit cannot be saved', async () => {
    renderNotes();
    await screen.findByLabelText('notes-list');
    fireEvent.click(screen.getByLabelText('note-edit-n1'));
    fireEvent.change(screen.getByLabelText('note-edit-input-n1'), { target: { value: '  ' } });
    expect(screen.getByLabelText('note-edit-save-n1')).toBeDisabled();

    fireEvent.click(screen.getByLabelText('note-edit-cancel-n1'));

    expect(screen.getByLabelText('note-body-n1')).toHaveTextContent('Klient prosi o inny kolor');
    expect(notesApi.updateProjectNote).not.toHaveBeenCalled();
  });

  it('removes a note only after the second tap, and the first tap can be taken back', async () => {
    vi.mocked(notesApi.deleteProjectNote).mockResolvedValue(undefined);
    renderNotes();
    await screen.findByLabelText('notes-list');

    fireEvent.click(screen.getByLabelText('note-delete-n1'));
    expect(notesApi.deleteProjectNote).not.toHaveBeenCalled();
    expect(screen.getByText('Usunąć tę notatkę?')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('note-delete-cancel-n1'));
    expect(screen.queryByText('Usunąć tę notatkę?')).toBeNull();
    expect(screen.getByLabelText('note-body-n1')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('note-delete-n1'));
    fireEvent.click(screen.getByLabelText('note-delete-confirm-n1'));

    await waitFor(() => expect(notesApi.deleteProjectNote).toHaveBeenCalledWith(projectId, 'n1'));
    await waitFor(() => expect(screen.queryByLabelText('note-n1')).toBeNull());
    expect(screen.getByLabelText('note-n2')).toBeInTheDocument();
  });

  it('keeps the note and says so when removing fails', async () => {
    vi.mocked(notesApi.deleteProjectNote).mockRejectedValue(new Error('boom'));
    renderNotes();
    await screen.findByLabelText('notes-list');
    fireEvent.click(screen.getByLabelText('note-delete-n1'));
    fireEvent.click(screen.getByLabelText('note-delete-confirm-n1'));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByLabelText('note-n1')).toBeInTheDocument();
  });

  it('says it could not load and tries again on tap', async () => {
    vi.mocked(notesApi.fetchProjectNotes).mockRejectedValueOnce(new Error('offline'));
    renderNotes();

    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać notatek.');
    fireEvent.click(screen.getByLabelText('notes-retry'));

    expect(await screen.findByLabelText('notes-list')).toBeInTheDocument();
    expect(notesApi.fetchProjectNotes).toHaveBeenCalledTimes(2);
  });

  it('speaks Russian, and long words stay inside the card (wrapping classes, compact 40 px controls)', async () => {
    localStorage.setItem('locale', 'ru');
    renderNotes();

    expect(await screen.findByLabelText('note-add')).toHaveTextContent('Добавить заметку');
    expect(screen.getByLabelText('note-edit-n2')).toHaveTextContent('Изменить');
    expect(screen.getByLabelText('note-delete-n2')).toHaveTextContent('Удалить');
    expect(screen.getByLabelText('note-body-n2').className).toContain('break-words');
    expect(screen.getByLabelText('note-body-n2').className).toContain('whitespace-pre-wrap');
    for (const label of ['note-add', 'note-edit-n2', 'note-delete-n2']) expect(screen.getByLabelText(label).className).toContain('min-h-10');
    expect(screen.getByLabelText('note-time-n2').textContent).toMatch(/15\.10\.2026/);
  });
});

describe('formatNoteTime', () => {
  it('reads an instant with or without a zone and falls back to the raw text', () => {
    expect(formatNoteTime('2026-10-15T12:30:00Z', 'pl')).toMatch(/15\.10\.2026/);
    expect(formatNoteTime('2026-10-15T12:30:00', 'pl')).toBe(formatNoteTime('2026-10-15T12:30:00Z', 'pl'));
    expect(formatNoteTime('not a date', 'pl')).toBe('not a date');
  });
});
