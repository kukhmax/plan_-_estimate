import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { SurfaceNote } from './SurfaceNote';

afterEach(cleanup);

describe('SurfaceNote', () => {
  it('is a separate, readable block: its own box, normal-size text that wraps, the note role', () => {
    render(<SurfaceNote surfaceId="s1" text={'Нужно перемерить\nвторая строка очень_длинного_слова_без_пробелов_очень_длинного_слова_без_пробелов'} />);
    const note = screen.getByRole('note');
    expect(note).toHaveAttribute('aria-label', 'surface-note-s1');
    expect(note).toHaveTextContent('Нужно перемерить');
    for (const cls of ['border', 'bg-amber-50', 'text-sm', 'break-words', 'whitespace-pre-wrap']) expect(note.className).toContain(cls);
    expect(note.className).not.toContain('text-xs');
  });
});
