import { Ico } from './Ico';

/**
 * The note of a wall (what the owner wrote in "Opis / notatki", e.g. "needs re-measuring"): a clearly separate block, not a grey line that reads as the heading of what follows it
 * ("Rodzaje prac i jakość"). Long text wraps; line breaks are kept.
 */
export function SurfaceNote({ surfaceId, text }: { surfaceId: string; text: string }) {
  return (
    <div
      role="note"
      aria-label={`surface-note-${surfaceId}`}
      className="my-1 rounded-lg border border-amber-300 border-l-4 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900 break-words whitespace-pre-wrap"
    >
      <Ico>📝</Ico>
      {text}
    </div>
  );
}
