import '@testing-library/jest-dom';
import { vi } from 'vitest';

// V2-13: every test starts with every trade on and no real request. A real `GET /api/trades` that fails in a test would mark the whole application offline (like any failed request)
// and stop the upload queue of the tests that count uploads. A test of the trades mocks the module itself, which replaces this.
vi.mock('../api/trades', async () => {
  const { CATALOG } = await import('./tradesFixture');
  return { fetchTrades: vi.fn(async () => CATALOG), saveTrades: vi.fn(async (enabled: string[]) => ({ ...CATALOG, enabled })) };
});
