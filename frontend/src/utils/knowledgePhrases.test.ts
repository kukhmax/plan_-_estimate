import { describe, expect, it } from 'vitest';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import { clientPhraseText } from './knowledgePhrases';

// The catalogue lives in the backend. The frontend image is built from frontend/ alone (no backend folder, and no tests run there), so the
// file is found by a glob: it is read in the repository, and simply absent in that image.
const found = import.meta.glob('../../../backend/app/domain/knowledge/catalog/situations.json', { eager: true, import: 'default' });
const catalog = (Object.values(found)[0] ?? []) as Array<{ outcomes: Array<{ phrases: string[] }> }>;
const codes = [...new Set(catalog.flatMap((situation) => situation.outcomes.flatMap((outcome) => outcome.phrases)))];

describe('clientPhraseText', () => {
  it('the catalog has phrases to check', () => {
    expect(codes.length).toBeGreaterThan(5);
  });

  it.each([
    ['pl', pl],
    ['ru', ru],
  ])('every phrase of every situation has its own words in %s', (_locale, dictionary) => {
    const t = dictionary as unknown as Parameters<typeof clientPhraseText>[0];
    for (const code of codes) {
      const text = clientPhraseText(t, code);
      expect(text, code).not.toBe(t.communication.fallback_phrase);
      expect(text, code).not.toContain('COMM_');
      expect(text.length, code).toBeGreaterThan(20);
    }
  });

  it('an unknown code shows the fallback sentence, never the code', () => {
    const t = pl as unknown as Parameters<typeof clientPhraseText>[0];
    expect(clientPhraseText(t, 'COMM_RISK_NOT_THERE')).toBe(pl.communication.fallback_phrase);
  });
});
