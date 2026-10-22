// Usability U-11: the application opens on the object the owner worked on last. The key carries the owner's id, so two accounts on one
// phone never meet; every access is guarded: a blocked or full storage (a private window, a cleared site) only means "nothing remembered".

const key = (ownerId: string) => `pe.lastProject.${ownerId}`;

export function readLastProject(ownerId: string): string | null {
  try {
    const value = window.localStorage.getItem(key(ownerId));
    return value && /^[0-9a-f-]{36}$/i.test(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeLastProject(ownerId: string, projectId: string): void {
  try {
    window.localStorage.setItem(key(ownerId), projectId);
  } catch {
    // the storage is unavailable: the next start simply opens the list
  }
}

export function clearLastProject(ownerId: string): void {
  try {
    window.localStorage.removeItem(key(ownerId));
  } catch {
    // nothing to clear
  }
}
