const SIDE = 112;

/**
 * A small picture (a data URL of at most ~112 px) of a photo that waits on the phone, kept next to it so that after the application
 * was closed the row can still show what the photo is. `null` where the browser cannot draw (the row then shows a grey square).
 */
export async function makeThumbnail(file: Blob): Promise<string | null> {
  try {
    if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return null;
    const bitmap = await createImageBitmap(file);
    try {
      const scale = Math.min(1, SIDE / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext('2d');
      if (!context) return null;
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const url = canvas.toDataURL('image/jpeg', 0.6);
      return url.startsWith('data:image/') ? url : null;
    } finally {
      bitmap.close?.();
    }
  } catch {
    return null; // a thumbnail is a convenience: the photo itself is kept regardless
  }
}
