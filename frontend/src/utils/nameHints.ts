import type { useI18n } from '../hooks/useI18n';

export type NameHintTexts = ReturnType<typeof useI18n>['t'];
type Texts = NameHintTexts;

/**
 * UX walk: the typical items of the trades and the materials are named in Polish (the names reach the Polish documents of the client), so a
 * Russian, Ukrainian or English screen showed "Punkt wodny", "Klej do płytek". These give the meaning in the language of the screen; null in
 * Polish or for a name the owner typed himself.
 */
export function packNameHint(t: Texts, name: string | null | undefined): string | null {
  if (!name) return null;
  const hint = (t.name_hints.pack as Record<string, string>)[name];
  return hint && hint !== name ? hint : null;
}

export function materialNameHint(t: Texts, code: string, name: string): string | null {
  const hint = (t.name_hints.material as Record<string, string>)[code];
  return hint && hint !== name ? hint : null;
}

/** "Punkt wodny (Точка водоснабжения)" -- the name with its meaning, for a single line such as an option of a list. */
export function withPackHint(t: Texts, name: string): string {
  const hint = packNameHint(t, name);
  return hint ? `${name} (${hint})` : name;
}
