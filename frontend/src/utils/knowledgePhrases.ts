import type { useI18n } from '../hooks/useI18n';
import { resolveKey } from './i18nKeys';

/**
 * The words the contractor says to the client for a phrase code of a situation outcome. The codes only name the phrase
 * (COMM_RISK_<RISK>, COMM_QUALITY_<SUBSTRATE>_<QUALITY>); the owner reads the sentence itself, in the interface language.
 * A phrase without a text yet never leaks its code to the screen.
 */
export function clientPhraseText(t: ReturnType<typeof useI18n>['t'], code: string): string {
  const key = code.startsWith('COMM_RISK_')
    ? `risk.${code.slice('COMM_RISK_'.length).toLowerCase()}.communication`
    : `communication.${code.toLowerCase()}.phrase`;
  const resolved = resolveKey(t, key);
  return resolved === key ? t.communication.fallback_phrase : resolved;
}
