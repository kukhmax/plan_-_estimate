import '@testing-library/jest-dom';
import { vi } from 'vitest';

// V2-13: every test starts with every trade on and no real request. A real `GET /api/trades` that fails in a test would mark the whole application offline (like any failed request)
// and stop the upload queue of the tests that count uploads. A test of the trades mocks the module itself, which replaces this.
vi.mock('../api/trades', async () => {
  const { CATALOG } = await import('./tradesFixture');
  return { fetchTrades: vi.fn(async () => CATALOG), saveTrades: vi.fn(async (enabled: string[]) => ({ ...CATALOG, enabled })) };
});

// UX walk: outside Telegram the application starts in the language of the phone; the tests run on a "Polish phone" unless one says otherwise
// (an own accessor, so `vi.spyOn(window.navigator, 'language', 'get')` still works)
Object.defineProperty(window.navigator, 'language', { get: () => 'pl-PL', configurable: true });

// UX walk: the hub of an object reads the state of the client's link; no test sends that request for real (a failed real request marks the
// application offline). A test of the link mocks the module itself, which replaces this.
vi.mock('../api/clientLink', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/clientLink')>()),
  fetchClientLink: vi.fn(async () => ({ link: null })),
}));
