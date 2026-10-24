/** V2-7a — "Moje dokumenty" in the knowledge base: the list, the window that adds a document, the card, the file, the chat. */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/knowledgeDocuments';
import { ApiError } from '../api/http';
import { I18nProvider } from '../hooks/useI18n';
import type { KnowledgeDocumentDetail, KnowledgeDocumentItem } from '../types/knowledgeDocument';
import { KnowledgeDocumentCard, KnowledgeDocumentsSection } from './KnowledgeDocuments';

vi.mock('../api/knowledgeDocuments', () => ({
  listKnowledgeDocuments: vi.fn(),
  fetchKnowledgeDocument: vi.fn(),
  saveKnowledgeDocument: vi.fn(),
  deleteKnowledgeDocument: vi.fn(),
  fetchKnowledgeDocumentFile: vi.fn(),
  sendKnowledgeDocumentToChat: vi.fn(),
}));

const ITEM = (n: number, overrides: Partial<KnowledgeDocumentItem> = {}): KnowledgeDocumentItem => ({
  id: `d${n}`, title: `Dokument ${n}`, kind: 'MANUFACTURER', source_url: null, doc_date: null, tags: [], file_name: null, file_mime: null,
  file_size: null, has_text: true, snippet: `Fragment ${n}`, updated_at: '2026-10-25T10:00:00Z', ...overrides,
});
const DETAIL = (overrides: Partial<KnowledgeDocumentDetail> = {}): KnowledgeDocumentDetail => ({
  ...ITEM(1), when_to_use: 'Przed gładzią', body: 'Gruntować dwa razy.\nPo wyschnięciu szpachlować.', created_at: '2026-10-25T09:00:00Z', ...overrides,
});
const LIST = (items: KnowledgeDocumentItem[]) => ({ items, total: items.length, max_documents: 100, max_file_bytes: 10_000_000 });

function section(onOpen = vi.fn(), query = '') {
  render(
    <I18nProvider>
      <KnowledgeDocumentsSection query={query} onOpen={onOpen} />
    </I18nProvider>,
  );
  return onOpen;
}

function card(onDeleted = vi.fn(), onChanged = vi.fn()) {
  render(
    <I18nProvider>
      <KnowledgeDocumentCard id="d1" onDeleted={onDeleted} onChanged={onChanged} />
    </I18nProvider>,
  );
  return { onDeleted, onChanged };
}

beforeEach(() => {
  localStorage.clear();
  delete window.Telegram;
  vi.clearAllMocks();
  vi.mocked(api.listKnowledgeDocuments).mockResolvedValue(LIST([]));
});

describe('the list of own documents', () => {
  it('says that there are none and offers the button that adds one', async () => {
    section();
    expect(await screen.findByLabelText('knowledge-documents-empty')).toHaveTextContent('Nie masz jeszcze własnych dokumentów');
    const add = screen.getByLabelText('knowledge-document-add');
    expect(add).toHaveTextContent('Dodaj dokument');
    expect(add.className).toContain('min-h-12');
  });

  it('shows the kind, the marks of the file / link / text and the tags of each document, five at first', async () => {
    const items = [
      ITEM(1, { file_name: 'k.pdf', file_mime: 'application/pdf', file_size: 1000, source_url: 'https://a.pl', tags: ['grunt', 'Knauf'] }),
      ...[2, 3, 4, 5, 6, 7].map((n) => ITEM(n)),
    ];
    vi.mocked(api.listKnowledgeDocuments).mockResolvedValue(LIST(items));
    const onOpen = section();
    const list = await screen.findByLabelText('knowledge-documents-list');
    expect(within(list).getAllByRole('listitem')).toHaveLength(5);
    expect(screen.getByLabelText('knowledge-documents-count')).toHaveTextContent('Dokumenty: 7');
    const first = screen.getByLabelText('knowledge-document-d1');
    expect(first).toHaveTextContent('Dokument 1');
    expect(first).toHaveTextContent('Karta techniczna producenta');
    expect(first).toHaveTextContent('grunt');
    expect(first).toHaveTextContent('Knauf');
    fireEvent.click(first);
    expect(onOpen).toHaveBeenCalledWith('d1');
    fireEvent.click(screen.getByLabelText('knowledge-documents-all'));
    expect(within(screen.getByLabelText('knowledge-documents-list')).getAllByRole('listitem')).toHaveLength(7);
  });

  it('asks the server with the words of the search and says so when nothing matches', async () => {
    section(vi.fn(), 'rekoj');
    await waitFor(() => expect(api.listKnowledgeDocuments).toHaveBeenCalledWith('rekoj'));
    expect(await screen.findByLabelText('knowledge-documents-empty')).toHaveTextContent('Brak własnych dokumentów dla tego zapytania');
  });

  it('offers a retry when the list does not load', async () => {
    vi.mocked(api.listKnowledgeDocuments).mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(LIST([ITEM(1)]));
    section();
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać dokumentów.');
    fireEvent.click(screen.getByLabelText('knowledge-documents-retry'));
    expect(await screen.findByLabelText('knowledge-document-d1')).toBeInTheDocument();
  });
});

describe('the window that adds a document', () => {
  async function open() {
    const onOpen = section();
    await screen.findByLabelText('knowledge-documents-empty');
    fireEvent.click(screen.getByLabelText('knowledge-document-add'));
    await screen.findByLabelText('knowledge-document-form');
    return onOpen;
  }

  it('has every field with touch-sized controls and the kinds to choose from', async () => {
    await open();
    for (const label of ['title', 'kind', 'url', 'file-pick', 'body', 'date', 'when', 'tags', 'save', 'cancel']) {
      const control = screen.getByLabelText(`knowledge-document-${label}`);
      if (label !== 'body' && label !== 'when') expect(control.className).toContain('min-h-1');
    }
    const kinds = [...screen.getByLabelText('knowledge-document-kind').querySelectorAll('option')].map((o) => o.getAttribute('value'));
    expect(kinds).toEqual(['STATUTE', 'NORM', 'MANUFACTURER', 'TEMPLATE', 'OTHER']);
    expect(screen.getByText('PDF, JPG lub PNG, do 10 MB.')).toBeInTheDocument();
  });

  it('refuses an empty name and a document with nothing in it, before asking the server', async () => {
    await open();
    fireEvent.click(screen.getByLabelText('knowledge-document-save'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Podaj nazwę dokumentu.');
    fireEvent.change(screen.getByLabelText('knowledge-document-title'), { target: { value: 'Norma' } });
    fireEvent.click(screen.getByLabelText('knowledge-document-save'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Dodaj tekst, link lub plik.');
    expect(api.saveKnowledgeDocument).not.toHaveBeenCalled();
  });

  it('sends every field and the chosen file, then opens the new document', async () => {
    vi.mocked(api.saveKnowledgeDocument).mockResolvedValue(DETAIL({ id: 'new1' }));
    const onOpen = await open();
    fireEvent.change(screen.getByLabelText('knowledge-document-title'), { target: { value: 'Karta Knauf' } });
    fireEvent.change(screen.getByLabelText('knowledge-document-kind'), { target: { value: 'NORM' } });
    fireEvent.change(screen.getByLabelText('knowledge-document-url'), { target: { value: 'https://knauf.pl' } });
    fireEvent.change(screen.getByLabelText('knowledge-document-body'), { target: { value: 'Tekst' } });
    fireEvent.change(screen.getByLabelText('knowledge-document-date'), { target: { value: '2026-03-01' } });
    fireEvent.change(screen.getByLabelText('knowledge-document-when'), { target: { value: 'Przed gładzią' } });
    fireEvent.change(screen.getByLabelText('knowledge-document-tags'), { target: { value: 'grunt, Knauf' } });
    const file = new File(['%PDF-1.4'], 'karta.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('knowledge-document-file'), { target: { files: [file] } });
    expect(screen.getByText('Wybrano: karta.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('knowledge-document-save'));
    await waitFor(() => expect(api.saveKnowledgeDocument).toHaveBeenCalled());
    expect(api.saveKnowledgeDocument).toHaveBeenCalledWith(null, {
      title: 'Karta Knauf', kind: 'NORM', source_url: 'https://knauf.pl', doc_date: '2026-03-01', when_to_use: 'Przed gładzią', body: 'Tekst',
      tags: 'grunt, Knauf', file, remove_file: false,
    });
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith('new1'));
    expect(screen.queryByLabelText('knowledge-document-form')).toBeNull();
  });

  it('does not take a file over 10 MB and says the code of the server in words', async () => {
    vi.mocked(api.saveKnowledgeDocument).mockRejectedValue(new ApiError('bad', 422, 'URL_INVALID', { code: 'URL_INVALID' }));
    await open();
    const big = new File([new Uint8Array(10_000_001)], 'big.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('knowledge-document-file'), { target: { files: [big] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Plik jest za duży (maks. 10 MB).');
    expect(screen.queryByText(/Wybrano/)).toBeNull();
    fireEvent.change(screen.getByLabelText('knowledge-document-title'), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText('knowledge-document-url'), { target: { value: 'knauf.pl' } });
    fireEvent.click(screen.getByLabelText('knowledge-document-save'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Link musi zaczynać się od http:// lub https://.');
  });

  it('does not hand its submit to a form that holds the screen (it is a portal)', async () => {
    const outer = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(
      <I18nProvider>
        <form onSubmit={outer}>
          <KnowledgeDocumentsSection query="" onOpen={vi.fn()} />
        </form>
      </I18nProvider>,
    );
    await screen.findByLabelText('knowledge-documents-empty');
    fireEvent.click(screen.getByLabelText('knowledge-document-add'));
    fireEvent.submit(await screen.findByLabelText('knowledge-document-form'));
    expect(outer).not.toHaveBeenCalled();
  });

  it('closes on Cancel and on Escape', async () => {
    await open();
    fireEvent.click(screen.getByLabelText('knowledge-document-cancel'));
    expect(screen.queryByLabelText('knowledge-document-form')).toBeNull();
    fireEvent.click(screen.getByLabelText('knowledge-document-add'));
    await screen.findByLabelText('knowledge-document-form');
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(screen.queryByLabelText('knowledge-document-form')).toBeNull();
  });
});

describe('one document', () => {
  it('shows the title, the kind, the tags, the date, "when to use" and the text', async () => {
    vi.mocked(api.fetchKnowledgeDocument).mockResolvedValue(DETAIL({ tags: ['grunt'], doc_date: '2026-03-01', source_url: 'https://knauf.pl/x' }));
    card();
    expect(await screen.findByText('Dokument 1')).toBeInTheDocument();
    expect(screen.getByText('grunt')).toBeInTheDocument();
    expect(screen.getByText(/Aktualne na dzień:/)).toBeInTheDocument();
    expect(screen.getByText('Przed gładzią')).toBeInTheDocument();
    expect(screen.getByLabelText('knowledge-document-body-text').textContent).toBe('Gruntować dwa razy.\nPo wyschnięciu szpachlować.');
    expect(screen.getByLabelText('knowledge-document-open-link')).toBeInTheDocument();
    expect(screen.queryByLabelText('knowledge-document-open-file')).toBeNull();
  });

  it('opens the link through Telegram when it can', async () => {
    const openLink = vi.fn();
    window.Telegram = { WebApp: { openLink, initData: 'x' } } as unknown as typeof window.Telegram;
    vi.mocked(api.fetchKnowledgeDocument).mockResolvedValue(DETAIL({ source_url: 'https://knauf.pl/x' }));
    card();
    fireEvent.click(await screen.findByLabelText('knowledge-document-open-link'));
    expect(openLink).toHaveBeenCalledWith('https://knauf.pl/x');
  });

  it('shows a picture inside the screen and a PDF only in the chat when inside Telegram', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    vi.mocked(api.fetchKnowledgeDocumentFile).mockResolvedValue(new Blob(['x']));
    window.Telegram = { WebApp: { initData: 'x' } } as unknown as typeof window.Telegram;
    vi.mocked(api.fetchKnowledgeDocument).mockResolvedValue(DETAIL({ file_name: 'strona.png', file_mime: 'image/png', file_size: 5000 }));
    const { unmount } = render(
      <I18nProvider>
        <KnowledgeDocumentCard id="d1" onDeleted={vi.fn()} onChanged={vi.fn()} />
      </I18nProvider>,
    );
    fireEvent.click(await screen.findByLabelText('knowledge-document-open-file'));
    expect(await screen.findByLabelText('knowledge-document-image')).toHaveAttribute('src', 'blob:x');
    fireEvent.click(screen.getByLabelText('knowledge-document-image-close'));
    expect(screen.queryByLabelText('knowledge-document-image')).toBeNull();
    unmount();
    vi.mocked(api.fetchKnowledgeDocument).mockResolvedValue(DETAIL({ file_name: 'karta.pdf', file_mime: 'application/pdf', file_size: 5000 }));
    card();
    expect(await screen.findByLabelText('knowledge-document-send')).toBeInTheDocument();
    expect(screen.queryByLabelText('knowledge-document-open-file')).toBeNull();
  });

  it('sends the file to the chat and says what Telegram answered', async () => {
    vi.mocked(api.fetchKnowledgeDocument).mockResolvedValue(DETAIL({ file_name: 'karta.pdf', file_mime: 'application/pdf', file_size: 5000 }));
    vi.mocked(api.sendKnowledgeDocumentToChat).mockResolvedValueOnce({ sent: true }).mockRejectedValueOnce(new ApiError('x', 409, 'TELEGRAM_CHAT_UNAVAILABLE', {}));
    card();
    fireEvent.click(await screen.findByLabelText('knowledge-document-send'));
    expect(await screen.findByRole('status')).toHaveTextContent('Plik wysłany do czatu z botem.');
    fireEvent.click(screen.getByLabelText('knowledge-document-send'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Bot nie może napisać na Twój czat');
  });

  it('changes the document in the same window and shows the saved one', async () => {
    vi.mocked(api.fetchKnowledgeDocument).mockResolvedValue(DETAIL({ tags: ['grunt', 'Knauf'], file_name: 'k.pdf', file_mime: 'application/pdf', file_size: 1200 }));
    vi.mocked(api.saveKnowledgeDocument).mockResolvedValue(DETAIL({ title: 'Nowy tytuł' }));
    const { onChanged } = card();
    fireEvent.click(await screen.findByLabelText('knowledge-document-edit'));
    expect(await screen.findByLabelText('knowledge-document-title')).toHaveValue('Dokument 1');
    expect(screen.getByLabelText('knowledge-document-tags')).toHaveValue('grunt, Knauf');
    expect(screen.getByText('Aktualny plik: k.pdf (1 KB)')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('knowledge-document-file-remove'));
    fireEvent.change(screen.getByLabelText('knowledge-document-title'), { target: { value: 'Nowy tytuł' } });
    fireEvent.click(screen.getByLabelText('knowledge-document-save'));
    await waitFor(() => expect(api.saveKnowledgeDocument).toHaveBeenCalledWith('d1', expect.objectContaining({ title: 'Nowy tytuł', file: null, remove_file: true })));
    expect(await screen.findByText('Nowy tytuł')).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it('deletes for good only after a second, explicit tap', async () => {
    vi.mocked(api.fetchKnowledgeDocument).mockResolvedValue(DETAIL());
    vi.mocked(api.deleteKnowledgeDocument).mockResolvedValue(undefined);
    const { onDeleted, onChanged } = card();
    fireEvent.click(await screen.findByLabelText('knowledge-document-delete'));
    expect(api.deleteKnowledgeDocument).not.toHaveBeenCalled();
    expect(screen.getByLabelText('knowledge-document-delete-confirm')).toHaveTextContent('„Dokument 1” zostanie usunięty razem z plikiem');
    fireEvent.click(screen.getByLabelText('knowledge-document-delete-no'));
    expect(screen.queryByLabelText('knowledge-document-delete-confirm')).toBeNull();
    fireEvent.click(screen.getByLabelText('knowledge-document-delete'));
    fireEvent.click(screen.getByLabelText('knowledge-document-delete-yes'));
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(api.deleteKnowledgeDocument).toHaveBeenCalledWith('d1');
    expect(onChanged).toHaveBeenCalled();
  });

  it('offers a retry when the document does not load', async () => {
    vi.mocked(api.fetchKnowledgeDocument).mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(DETAIL());
    card();
    fireEvent.click(await screen.findByLabelText('knowledge-document-retry'));
    expect(await screen.findByText('Dokument 1')).toBeInTheDocument();
  });

  it('speaks Ukrainian and English too', async () => {
    for (const [lang, add] of [['uk', 'Додати документ'], ['en', 'Add a document'], ['ru', 'Добавить документ']] as const) {
      localStorage.setItem('locale', lang);
      const { unmount } = render(
        <I18nProvider>
          <KnowledgeDocumentsSection query="" onOpen={vi.fn()} />
        </I18nProvider>,
      );
      expect(await screen.findByLabelText('knowledge-document-add')).toHaveTextContent(add);
      unmount();
    }
  });
});
