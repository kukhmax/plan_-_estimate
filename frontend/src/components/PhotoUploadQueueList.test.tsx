import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { classifyPhotoError } from '../utils/photoErrors';
import { QueueItem } from '../utils/photoUploadQueue';
import { ApiError } from '../api/http';
import { PhotoUploadQueueList } from './PhotoUploadQueueList';

function item(over: Partial<QueueItem> = {}): QueueItem {
  return {
    id: 'q1',
    uploadId: 'u1',
    file: new File(['x'], 'IMG_0001.jpg', { type: 'image/jpeg' }),
    target: { projectId: 'p', context: 'PROJECT' },
    source: 'CAMERA',
    state: 'queued',
    progress: 0,
    attempt: 0,
    previewUrl: null,
    error: null,
    result: null,
    notBefore: 0,
    networkRetries: 0,
    busyRetried: false,
    ...over,
  };
}

const failure = (status: number, code: string) => classifyPhotoError(new ApiError('x', status, code));

function renderList(items: QueueItem[]) {
  const handlers = { onCancel: vi.fn(), onRetry: vi.fn(), onRetryAsNew: vi.fn(), onDismiss: vi.fn() };
  const view = render(
    <I18nProvider>
      <PhotoUploadQueueList items={items} {...handlers} />
    </I18nProvider>,
  );
  return { ...handlers, ...view };
}

describe('PhotoUploadQueueList', () => {
  beforeEach(() => localStorage.clear());

  it('renders nothing for an empty queue', () => {
    const { container } = renderList([]);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the state of each row with progress for an upload in flight', () => {
    renderList([
      item({ id: 'a', state: 'queued' }),
      item({ id: 'b', state: 'uploading', progress: 0.42 }),
      item({ id: 'c', state: 'processing', progress: 1 }),
      item({ id: 'd', state: 'done', progress: 1 }),
      item({ id: 'e', state: 'canceled' }),
    ]);
    expect(screen.getByText('Oczekuje')).toBeInTheDocument();
    expect(screen.getByText('Wysyłanie… 42%')).toBeInTheDocument();
    expect(screen.getByText('Przetwarzanie…')).toBeInTheDocument();
    expect(screen.getByText('Gotowe')).toBeInTheDocument();
    expect(screen.getByText('Anulowano')).toBeInTheDocument();
    const bars = screen.getAllByRole('progressbar');
    expect(bars).toHaveLength(2); // uploading + processing
    expect(bars[0]).toHaveAttribute('aria-valuenow', '42');
    expect(bars[0].firstElementChild).toHaveStyle({ width: '42%' });
  });

  it('localizes states in Russian', () => {
    localStorage.setItem('locale', 'ru');
    renderList([item({ state: 'uploading', progress: 0.5 })]);
    expect(screen.getByText('Отправка… 50%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отмена' })).toBeInTheDocument();
  });

  it('shows a localized message, never server text, for a failed row', () => {
    renderList([item({ state: 'failed', error: failure(415, 'PHOTO_UNSUPPORTED_FORMAT') })]);
    expect(screen.getByRole('alert')).toHaveTextContent('Użyj JPEG, PNG lub WebP.');
  });

  it('offers only the actions that make sense per row', () => {
    const { onCancel, onRetry, onRetryAsNew, onDismiss } = renderList([
      item({ id: 'active', state: 'uploading', progress: 0.1 }),
      item({ id: 'net', state: 'failed', error: failure(0, 'NETWORK_ERROR') }),
      item({ id: 'conflict', state: 'failed', error: failure(409, 'PHOTO_UPLOAD_ID_CONFLICT') }),
      item({ id: 'bad', state: 'failed', error: failure(422, 'PHOTO_INVALID_IMAGE') }),
    ]);
    const rows = screen.getAllByRole('listitem');
    const names = (row: HTMLElement) => within(row).queryAllByRole('button').map((b) => b.textContent);
    expect(names(rows[0])).toEqual(['Anuluj']); // active: cancel only
    expect(names(rows[1])).toEqual(['Ponów', 'Zamknij']); // retryable
    expect(names(rows[2])).toEqual(['Ponów jako nowe', 'Zamknij']); // identity conflict: explicit new id only
    expect(names(rows[3])).toEqual(['Zamknij']); // unusable image: dismiss only

    fireEvent.click(within(rows[0]).getByRole('button', { name: 'Anuluj' }));
    expect(onCancel).toHaveBeenCalledWith('active');
    fireEvent.click(within(rows[1]).getByRole('button', { name: 'Ponów' }));
    expect(onRetry).toHaveBeenCalledWith('net');
    fireEvent.click(within(rows[2]).getByRole('button', { name: 'Ponów jako nowe' }));
    expect(onRetryAsNew).toHaveBeenCalledWith('conflict');
    fireEvent.click(within(rows[3]).getByRole('button', { name: 'Zamknij' }));
    expect(onDismiss).toHaveBeenCalledWith('bad');
  });

  it('lets a finished row be dismissed', () => {
    const { onDismiss } = renderList([item({ state: 'done', progress: 1 })]);
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }));
    expect(onDismiss).toHaveBeenCalledWith('q1');
  });

  it('shows the local preview when there is one', () => {
    renderList([item({ previewUrl: 'blob:abc' })]);
    expect(screen.getByRole('img')).toHaveAttribute('src', 'blob:abc');
  });

  it('mobile: long names and long Russian errors wrap, actions stack on their own line with ≥ 44 px targets', () => {
    localStorage.setItem('locale', 'ru');
    const longName = `${'очень_длинное_имя_файла_'.repeat(8)}.jpg`;
    renderList([
      item({
        file: new File(['x'], longName, { type: 'image/jpeg' }),
        state: 'failed',
        error: failure(503, 'PHOTO_STORAGE_UNAVAILABLE'),
      }),
    ]);
    const name = screen.getByText(longName);
    expect(name).toHaveClass('break-all');
    expect(name.parentElement).toHaveClass('min-w-0');
    expect(screen.getByRole('alert')).toHaveClass('break-words');
    const retry = screen.getByRole('button', { name: 'Повторить' });
    expect(retry).toHaveClass('min-h-11');
    expect(retry.parentElement).toHaveClass('flex', 'flex-wrap');
  });

  it('uses theme tokens only (dark mode)', () => {
    const { container } = renderList([item({ state: 'failed', error: failure(0, 'NETWORK_ERROR') })]);
    expect(container.innerHTML).toContain('var(--tg-');
    expect(container.innerHTML).not.toMatch(/bg-white|text-slate|border-slate/);
  });
});
