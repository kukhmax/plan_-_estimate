import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { abandonContractDraft, fetchContractGate, fetchContracts, issueContract, openContractDraft, saveContractAnswers } from './contracts';

function respond(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: status < 400, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response);
}

describe('contracts API (Stages 16E.1 / 16E.2)', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'tok');
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  const call = () => {
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    return { url: String(url), init: (init ?? {}) as RequestInit };
  };

  it('reads the contracts and opens the draft with a POST', async () => {
    respond(200, { items: [], total: 0 });
    await fetchContracts('p1');
    expect(call().url).toBe('/api/projects/p1/contracts');
    vi.mocked(fetch).mockClear();
    respond(201, {});
    await openContractDraft('p1');
    expect(call().url).toBe('/api/projects/p1/contracts');
    expect(call().init.method).toBe('POST');
  });

  it('patches only the answers it is given, with null clearing one', async () => {
    respond(200, {});
    await saveContractAnswers('p1', 'c1', { contract_place: 'Kraków', advance_percent: null });
    expect(call().url).toBe('/api/projects/p1/contracts/c1/answers');
    expect(call().init.method).toBe('PATCH');
    expect(JSON.parse(String(call().init.body))).toEqual({ answers: { contract_place: 'Kraków', advance_percent: null } });
  });

  it('asks the gate, issues and abandons through their own routes', async () => {
    respond(200, { ready: true, blockers: [] });
    await fetchContractGate('p1', 'c1');
    expect(call().url).toBe('/api/projects/p1/contracts/c1/gate');
    vi.mocked(fetch).mockClear();
    respond(202, {});
    await issueContract('p1', 'c1');
    expect(call().url).toBe('/api/projects/p1/contracts/c1/issue');
    expect(call().init.method).toBe('POST');
    vi.mocked(fetch).mockClear();
    respond(200, {});
    await abandonContractDraft('p1', 'c1');
    expect(call().url).toBe('/api/projects/p1/contracts/c1/archive');
  });
});
