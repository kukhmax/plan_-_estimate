import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchContractCatalog } from './contractCatalog';
import { resolveKey } from '../utils/i18nKeys';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';

const base = import.meta.env.VITE_API_URL ?? '';

const catalog = {
  requirements: { version: 1, items: [{ key: 'windows_glazed', group: 'GLAZING', value_kind: 'YES_NO', unit: null, label_key: 'contractCatalog.requirements.windows_glazed', text_pl: 'Okna zamontowane i oszklone' }] },
  instruments: { version: 1, items: [] },
  evaluation: { version: 1, items: [] },
  defects: { version: 1, items: [] },
  tolerances: { version: 1, items: [] },
  questionnaire: { version: 1, items: [{ key: 'who_accepts', group: 'PARTIES', kind: 'PERSON_LIST', requirement: 'REQUIRED', default: null, options: null, unit: null, label_key: 'contractCatalog.questions.who_accepts', hint_key: 'contractCatalog.hints.who_accepts' }] },
};

describe('fetchContractCatalog (Stage 16B.3)', () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];

  beforeEach(() => {
    calls.length = 0;
    localStorage.setItem('access_token', 'test-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        return new Response(JSON.stringify(catalog), { status: 200 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('reads the catalogues with one GET', async () => {
    const result = await fetchContractCatalog();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`${base}/api/contract-catalog`);
    expect(calls[0].init?.method ?? 'GET').toBe('GET');
    expect(result.questionnaire.items[0].key).toBe('who_accepts');
  });

  it('every label_key and hint_key the server sends resolves to a text in PL and in RU', () => {
    const keys = [catalog.requirements.items[0].label_key, catalog.questionnaire.items[0].label_key, catalog.questionnaire.items[0].hint_key];
    for (const dictionary of [pl, ru]) {
      for (const key of keys) {
        const text = resolveKey(dictionary, key as string);
        expect(text).not.toBe(key);
        expect(text.trim().length).toBeGreaterThan(0);
      }
    }
  });
});
