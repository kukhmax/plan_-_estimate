/** Owner 2026-10-31: "Dodatkowo" of the summary of an object -- the money, the dates and the open high risks, read only when opened. */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as calendarApi from '../api/calendar';
import * as estimatesApi from '../api/estimates';
import * as paymentScheduleApi from '../api/paymentSchedule';
import { I18nProvider } from '../hooks/useI18n';
import { ProjectSummaryMore } from './ProjectSummaryMore';

vi.mock('../api/estimates', () => ({ listEstimates: vi.fn() }));
vi.mock('../api/paymentSchedule', () => ({ fetchSchedule: vi.fn() }));
vi.mock('../api/calendar', () => ({ fetchSchedule: vi.fn() }));

function show(risks = [{ room_id: 'r1', room_name: 'Salon', count: 2 }]) {
  render(
    <I18nProvider>
      <ProjectSummaryMore projectId="p1" risks={risks} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(estimatesApi.listEstimates).mockResolvedValue({
    items: [
      { id: 'e1', version: 1, status: 'ARCHIVED', total: '10.00', gross_total: null, currency: 'PLN' },
      { id: 'e2', version: 2, status: 'ACCEPTED', total: '14581.02', gross_total: null, currency: 'PLN' },
    ],
    total: 2,
  } as never);
  vi.mocked(paymentScheduleApi.fetchSchedule).mockResolvedValue({
    items: [
      { id: 's1', title: 'Zaliczka', due_on: '2026-11-02', state: 'PAID' },
      { id: 's2', title: 'Etap 2', due_on: '2026-11-20', state: 'OPEN' },
    ],
    summary: { agreed: '14581.02', stages_total: '14581.02', unpriced: 0, difference: '0.00', received: '4000.00', to_receive: '10581.02' },
  } as never);
  vi.mocked(calendarApi.fetchSchedule).mockResolvedValue({
    planned: [{ occurrence_key: 'a', planned_date: '2026-11-10' }, { occurrence_key: 'b', planned_date: '2026-11-03' }],
    warnings: [], window_start: null, window_end: null,
  });
});

describe('Dodatkowo of the summary of an object', () => {
  it('reads nothing until it is opened, then shows the money, the dates and the risks', async () => {
    show();
    expect(estimatesApi.listEstimates).not.toHaveBeenCalled();
    const more = screen.getByLabelText('object-summary-more');
    expect(more).toHaveClass('min-h-11');
    fireEvent.click(more);
    expect(await screen.findByLabelText('object-summary-estimate')).toHaveTextContent('Wersja 2');
    expect(screen.getByLabelText('object-summary-estimate')).toHaveTextContent('Zaakceptowany');
    expect(screen.getByLabelText('object-summary-received')).toHaveTextContent('4');
    expect(screen.getByLabelText('object-summary-to-receive')).toHaveTextContent('10');
    expect(screen.getByLabelText('object-summary-works')).toHaveTextContent('03.11.2026 – 10.11.2026');
    expect(screen.getByLabelText('object-summary-next-stage')).toHaveTextContent('Etap 2 · 20.11.2026');
    expect(screen.getByLabelText('object-summary-risk-r1')).toHaveTextContent('Salon');
    expect(screen.getByLabelText('object-summary-risk-r1')).toHaveTextContent('⚠ 2');
  });

  it('says there are no open high risks and shows "—" for what could not be read', async () => {
    vi.mocked(paymentScheduleApi.fetchSchedule).mockRejectedValue(new Error('down'));
    show([]);
    fireEvent.click(screen.getByLabelText('object-summary-more'));
    expect(await screen.findByLabelText('object-summary-no-risks')).toBeInTheDocument();
    expect(screen.getByLabelText('object-summary-next-stage')).toHaveTextContent('—');
  });
});
