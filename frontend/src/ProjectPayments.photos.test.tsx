import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as paymentsApi from './api/payments';
import { buildUploadFormData } from './api/photos';
import { ProjectPayments } from './components/ProjectPayments';
import { I18nProvider } from './hooks/useI18n';
import { photoKey, ProjectPhotosContext, type ProjectPhotosValue } from './hooks/ProjectPhotosContext';
import { adjustPhotoCounts, EMPTY_PHOTO_COUNTS, photoCountFor, totalPhotoCount } from './hooks/usePhotoCounts';
import type { Payment, PaymentList } from './types/payment';
import type { PhotoAttachmentRead, PhotoCounts } from './types/photo';
import { attachmentTarget, targetIdOf } from './utils/photoTarget';

vi.mock('./api/payments', () => ({
  fetchPayments: vi.fn(),
  createPayment: vi.fn(),
  updatePayment: vi.fn(),
  archivePayment: vi.fn(),
  restorePayment: vi.fn(),
  fetchFinance: vi.fn(),
  saveAgreedAmount: vi.fn(),
}));
const sectionProps = vi.fn();
vi.mock('./components/PhotoSection', () => ({
  PhotoSection: (props: Record<string, unknown>) => {
    sectionProps(props);
    return <div data-testid="photo-section" />;
  },
}));

const projectId = '11111111-1111-1111-1111-111111111111';
const payment = (over: Partial<Payment>): Payment => ({
  id: 'p0', project_id: projectId, kind: 'INVOICE', title: 'Faktura', number: null, amount_gross: '100.00', amount_net: null, vat_rate: null,
  occurred_on: '2026-10-01', due_on: null, settles_id: null, counterparty: null, document_kind: null, note: null, is_archived: false,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z', settled: '0.00', remaining: '100.00', state: 'OPEN', ...over,
});
const INVOICE = payment({ id: 'inv1', title: 'Faktura za etap 1' });
const EXPENSE = payment({ id: 'exp1', kind: 'EXPENSE', title: 'Farba', counterparty: 'Castorama', document_kind: 'RECEIPT', settled: null, remaining: null, state: null });
const ADVANCE = payment({ id: 'adv1', kind: 'ADVANCE', title: 'Zaliczka', settled: null, remaining: null, state: null });

const LIST: PaymentList = {
  items: [INVOICE, EXPENSE, ADVANCE],
  total: 3,
  summary: { invoiced: '100.00', received: '0.00', expenses: '0.00', invoiced_unpaid: '100.00', to_receive: null, result: '0.00' },
  agreed_amount: null,
};

function provided(counts: Partial<PhotoCounts>, expanded: string[] = []): ProjectPhotosValue {
  return {
    projectId,
    counts: { ...EMPTY_PHOTO_COUNTS, ...counts },
    isExpanded: (key) => expanded.includes(key),
    toggle: vi.fn(),
    adjust: vi.fn(),
    resolveLocation: vi.fn(() => ''),
    ensureLocations: vi.fn(),
  };
}

function renderScreen(value: ProjectPhotosValue | null) {
  return render(
    <I18nProvider>
      <ProjectPhotosContext.Provider value={value}>
        <ProjectPayments projectId={projectId} />
      </ProjectPhotosContext.Provider>
    </I18nProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(paymentsApi.fetchPayments).mockResolvedValue(LIST);
});

describe('the receipts on the cards of the settlements (IA-3)', () => {
  it('every card has a photo button with the number of ITS photos, on each of the three tabs', async () => {
    renderScreen(provided({ payments: { inv1: 2, exp1: 5, other: 9 } }));
    const invoice = await screen.findByLabelText('payment-inv1');
    expect(within(invoice).getByRole('button', { name: 'Zdjęcia: 2' })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('payments-tab-client'));
    expect(within(screen.getByLabelText('payment-adv1')).getByRole('button', { name: 'Zdjęcia: 0' })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('payments-tab-materials'));
    expect(within(screen.getByLabelText('payment-exp1')).getByRole('button', { name: 'Zdjęcia: 5' })).toBeInTheDocument();
  });

  it('the button opens and closes the photos of that record only', async () => {
    const value = provided({ payments: { inv1: 1 } });
    renderScreen(value);
    const invoice = await screen.findByLabelText('payment-inv1');
    fireEvent.click(within(invoice).getByRole('button', { name: 'Zdjęcia: 1' }));
    expect(value.toggle).toHaveBeenCalledWith(photoKey('PAYMENT', 'inv1'));
    expect(screen.queryByTestId('photo-section')).toBeNull(); // nothing opens by itself
  });

  it('an open record shows its photo section with upload allowed, for its own record and context', async () => {
    renderScreen(provided({}, [photoKey('PAYMENT', 'inv1')]));
    await screen.findByLabelText('payment-inv1');
    expect(screen.getAllByTestId('photo-section')).toHaveLength(1);
    expect(sectionProps).toHaveBeenCalledWith(expect.objectContaining({ context: 'PAYMENT', targetId: 'inv1', allowUpload: true, projectId }));
  });

  it('names the place of its photos by the settlements and the record, not by "Obiekt"', async () => {
    renderScreen(provided({}, [photoKey('PAYMENT', 'inv1')]));
    await screen.findByLabelText('payment-inv1');
    expect(sectionProps).toHaveBeenCalledWith(expect.objectContaining({ locationLabel: 'Faktury i zaliczki → Faktura za etap 1' }));
  });

  it('the section sits inside the card of its record, under its header', async () => {
    renderScreen(provided({}, [photoKey('PAYMENT', 'inv1')]));
    const invoice = await screen.findByLabelText('payment-inv1');
    expect(within(invoice).getByTestId('photo-section')).toBeInTheDocument();
    expect(within(screen.getByLabelText('payments-list')).getAllByRole('listitem')).toHaveLength(1);
  });

  it('the screen works without a photo context (no button, nothing broken)', async () => {
    renderScreen(null);
    const invoice = await screen.findByLabelText('payment-inv1');
    expect(within(invoice).queryByRole('button', { name: /Zdjęcia/ })).toBeNull();
    expect(within(invoice).getByLabelText('payment-edit-inv1')).toBeInTheDocument();
  });

  it('keeps the photo button at least 44 px high and Russian words in Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderScreen(provided({ payments: { inv1: 3 } }));
    const invoice = await screen.findByLabelText('payment-inv1');
    const button = within(invoice).getByRole('button', { name: /Фото: 3/ });
    expect(button.className).toContain('min-h-11');
  });
});

describe('counts of receipts', () => {
  const counts: PhotoCounts = { ...EMPTY_PHOTO_COUNTS, project: 2, rooms: { r1: 1 }, surfaces: { s1: 1 }, openings: { o1: 1 }, payments: { inv1: 4 } };

  it('reads the number of a record, zero when it has none or when the server does not know receipts', () => {
    expect(photoCountFor(counts, 'PAYMENT', 'inv1')).toBe(4);
    expect(photoCountFor(counts, 'PAYMENT', 'unknown')).toBe(0);
    expect(photoCountFor(counts, 'PAYMENT', undefined)).toBe(0);
    const { payments: _omitted, ...old } = counts;
    expect(photoCountFor(old as PhotoCounts, 'PAYMENT', 'inv1')).toBe(0);
  });

  it('never counts receipts among the photos of the object', () => {
    expect(totalPhotoCount(counts)).toBe(2 + 1 + 1 + 1);
  });

  it('adjusts the record only; a receipt never moves a room, a surface or the object, nothing goes below zero and emptied entries go', () => {
    const more = adjustPhotoCounts(counts, 'PAYMENT', 'inv1', 1, 'r1');
    expect(more.payments).toEqual({ inv1: 5 });
    expect({ ...more, payments: undefined }).toEqual({ ...counts, payments: undefined });
    expect(adjustPhotoCounts(counts, 'PAYMENT', 'inv1', -9).payments).toEqual({});
    expect(adjustPhotoCounts(counts, 'PAYMENT', 'new', 1).payments).toEqual({ inv1: 4, new: 1 });
    expect(counts.payments).toEqual({ inv1: 4 }); // not mutated
    expect(adjustPhotoCounts({ ...counts, payments: undefined }, 'PAYMENT', 'inv1', 1).payments).toEqual({ inv1: 1 });
  });
});

describe('the address of a receipt', () => {
  it('names the record as the leaf of a target and of an attachment', () => {
    expect(targetIdOf({ context: 'PAYMENT', paymentId: 'inv1' })).toBe('inv1');
    expect(targetIdOf({ context: 'ROOM', roomId: 'r1', paymentId: 'inv1' })).toBe('r1');
    const attachment = { context: 'PAYMENT', room_id: null, surface_id: null, opening_id: null, inspection_id: null, finding_id: null, payment_id: 'inv1', question_id: null, occurrence_key: null } as unknown as PhotoAttachmentRead;
    expect(attachmentTarget(attachment)).toMatchObject({ context: 'PAYMENT', targetId: 'inv1' });
  });

  it('sends the record with the upload, and only for its own context', () => {
    const file = new File(['x'], 'r.jpg', { type: 'image/jpeg' });
    const receipt = buildUploadFormData({ projectId, uploadId: 'u1', context: 'PAYMENT', paymentId: 'inv1', file, source: 'CAMERA' });
    expect([...receipt.keys()]).toEqual(['upload_id', 'context', 'payment_id', 'source', 'file']);
    expect(receipt.get('payment_id')).toBe('inv1');
    const room = buildUploadFormData({ projectId, uploadId: 'u2', context: 'ROOM', roomId: 'r1', paymentId: 'inv1', file });
    expect(room.has('payment_id')).toBe(false);
    expect(buildUploadFormData({ projectId, uploadId: 'u3', context: 'PAYMENT', file }).has('payment_id')).toBe(false); // never half-addressed
  });
});
