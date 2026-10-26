import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/trades';
import { I18nProvider } from '../hooks/useI18n';
import { resetTrades } from '../hooks/useTrades';
import ru from '../locales/ru.json';
import { CATALOG } from '../test/tradesFixture';
import { TradesPicker } from './TradesPicker';

vi.mock('../api/trades', () => ({ fetchTrades: vi.fn(), saveTrades: vi.fn() }));

const renderPicker = () => render(<I18nProvider><TradesPicker /></I18nProvider>);

describe('TradesPicker (V2-13)', () => {
  beforeEach(() => {
    resetTrades();
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchTrades).mockResolvedValue(CATALOG);
  });
  afterEach(() => {
    cleanup();
    resetTrades();
  });

  it('offers the six trades in the order of the owner, all ticked for a new owner, with touch-sized rows', async () => {
    renderPicker();
    const boxes = await screen.findAllByRole('checkbox');
    expect(boxes.map((b) => b.getAttribute('aria-label'))).toEqual(['trade-FINISHING', 'trade-DRYWALL', 'trade-MICROCEMENT', 'trade-TILE', 'trade-ELECTRIC', 'trade-PLUMBING']);
    expect(boxes.every((b) => (b as HTMLInputElement).checked)).toBe(true);
    expect(screen.getByText('Mikrocement')).toBeInTheDocument();
    for (const box of boxes) expect(box.closest('label')?.className).toContain('min-h-11');
  });

  it('saves at once the choice without the unticked trade, in the order of the catalogue', async () => {
    vi.mocked(api.saveTrades).mockResolvedValue({ ...CATALOG, enabled: ['FINISHING', 'DRYWALL', 'TILE', 'ELECTRIC', 'PLUMBING'] });
    renderPicker();
    const microcement = await screen.findByLabelText('trade-MICROCEMENT');
    await act(async () => { fireEvent.click(microcement); });
    expect(api.saveTrades).toHaveBeenCalledWith(['FINISHING', 'DRYWALL', 'TILE', 'ELECTRIC', 'PLUMBING']);
    await waitFor(() => expect((screen.getByLabelText('trade-MICROCEMENT') as HTMLInputElement).checked).toBe(false));
    vi.mocked(api.saveTrades).mockResolvedValue(CATALOG);
    await act(async () => { fireEvent.click(screen.getByLabelText('trade-MICROCEMENT')); });
    expect(api.saveTrades).toHaveBeenLastCalledWith(['FINISHING', 'DRYWALL', 'MICROCEMENT', 'TILE', 'ELECTRIC', 'PLUMBING']);
  });

  it('says so when the choice could not be saved and keeps the old one', async () => {
    vi.mocked(api.saveTrades).mockRejectedValue(new Error('boom'));
    renderPicker();
    const tile = await screen.findByLabelText('trade-TILE');
    await act(async () => { fireEvent.click(tile); });
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się zapisać wyboru');
    expect((screen.getByLabelText('trade-TILE') as HTMLInputElement).checked).toBe(true);
  });

  it('shows no boxes and a retry while the server has not answered', async () => {
    vi.mocked(api.fetchTrades).mockRejectedValue(new Error('offline'));
    renderPicker();
    expect(await screen.findByLabelText('trades-retry')).toBeInTheDocument();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    vi.mocked(api.fetchTrades).mockResolvedValue(CATALOG);
    await act(async () => { fireEvent.click(screen.getByLabelText('trades-retry')); });
    expect(await screen.findAllByRole('checkbox')).toHaveLength(6);
  });

  it('speaks Russian when the language is Russian', async () => {
    localStorage.setItem('locale', 'ru');
    renderPicker();
    expect(await screen.findByText(ru.trades.names.MICROCEMENT)).toBeInTheDocument();
    expect(screen.getByText(ru.trades.title)).toBeInTheDocument();
  });
});
