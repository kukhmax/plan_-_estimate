/**
 * Asks the browser not to clear what the phone keeps for work without a signal (changes and photos waiting to be sent) when it runs
 * short of room (Stage 19F). Best effort: a WebView may refuse or not know the call; nothing depends on the answer.
 */
export async function requestPersistentStorage(): Promise<boolean> {
  try {
    const storage = typeof navigator !== 'undefined' ? navigator.storage : undefined;
    if (!storage || typeof storage.persist !== 'function') return false;
    if (typeof storage.persisted === 'function' && (await storage.persisted())) return true;
    return await storage.persist();
  } catch {
    return false;
  }
}
