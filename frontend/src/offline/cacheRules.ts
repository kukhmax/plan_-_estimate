/**
 * Which GET requests are kept on the phone for work without a signal (Stage 19B).
 *
 * Only what the owner needs on site: the object, its rooms and everything under them (surfaces, openings, rectangles of the floor
 * and the ceiling, inspections with answers, work plans, risks), the notes, the clients and the checklist templates.
 * (IA-4: also the settlement records of an object, `/payments`; their agreed amount, `/finance`, needs the server.)
 * Never kept: photos (their links expire), documents, estimates, the contract and the protocols, the price book, the calendar,
 * the knowledge base, authentication — those need the server and show "needs a connection".
 */
const CACHEABLE: readonly RegExp[] = [
  /^\/api\/projects(\?.*)?$/,
  /^\/api\/projects\/[0-9a-f-]{36}(\?.*)?$/i,
  /^\/api\/projects\/[0-9a-f-]{36}\/(summary|notes|payments)(\?.*)?$/i,
  /^\/api\/projects\/[0-9a-f-]{36}\/rooms(\/|\?|$)/i,
  /^\/api\/clients(\/|\?|$)/,
  /^\/api\/checklist-templates(\/|\?|$)/,
];

export function isCacheablePath(path: string): boolean {
  return CACHEABLE.some((rule) => rule.test(path));
}
