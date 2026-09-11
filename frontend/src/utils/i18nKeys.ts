/**
 * Resolve a dotted backend i18n key (e.g. "checklist.template.concrete.title")
 * against a locale dictionary object. Backend entity keys arrive as plain
 * dotted strings, unlike the statically-typed UI keys, so they must be walked.
 */
export function resolveKey(t: unknown, dotted: string): string {
  const parts = dotted.split('.');
  let node: unknown = t;
  for (const part of parts) {
    if (node && typeof node === 'object' && part in node) {
      node = (node as Record<string, unknown>)[part];
    } else {
      return dotted;
    }
  }
  return typeof node === 'string' ? node : dotted;
}
