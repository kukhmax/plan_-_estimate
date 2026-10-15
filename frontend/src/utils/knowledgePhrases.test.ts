import { describe, expect, it } from 'vitest';
import pl from '../locales/pl.json';
import ru from '../locales/ru.json';
import situations from '../../../backend/app/domain/knowledge/catalog/situations.json';
import { clientPhraseText } from './knowledgePhrases';

const catalog = situations as Array<{ outcomes: Array<{ phrases: string[] }> }>;
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
