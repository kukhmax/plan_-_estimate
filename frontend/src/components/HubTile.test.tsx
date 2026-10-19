import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { HubTile } from './HubTile';
import { ProjectHub } from './ProjectHub';

describe('HubTile: the soft colours of the tiles', () => {
  it('is white without a tone and amber when it is the accent, whatever tone it is given', () => {
    const { rerender } = render(<HubTile icon="x" ariaLabel="t" label="Plain" onOpen={() => {}} />);
    expect(screen.getByLabelText('t')).toHaveAttribute('data-tone', 'white');
    expect(screen.getByLabelText('t').className).toContain('pe-surface');
    rerender(<HubTile accent tone="green" icon="x" ariaLabel="t" label="Plain" onOpen={() => {}} />);
    expect(screen.getByLabelText('t')).toHaveAttribute('data-tone', 'accent');
    expect(screen.getByLabelText('t').className).toContain('bg-amber-500');
    expect(screen.getByLabelText('t').className).not.toContain('bg-green-100');
  });

  it.each([
    ['green', 'bg-green-100'],
    ['sky', 'bg-sky-100'],
    ['pink', 'bg-pink-100'],
    ['slate', 'bg-slate-200'],
    ['yellow', 'bg-yellow-100'],
  ] as const)('the tone %s gives %s and no white background', (tone, background) => {
    render(<HubTile tone={tone} icon="x" ariaLabel="t" label="Tile" onOpen={() => {}} />);
    const tile = screen.getByLabelText('t');
    expect(tile).toHaveAttribute('data-tone', tone);
    expect(tile.className).toContain(background);
    expect(tile.className).not.toContain('pe-surface');
    expect(tile.className).toContain('min-h-14');
  });

  it('still opens, and keeps the number on the right readable on a coloured tile', () => {
    const open = vi.fn();
    render(<HubTile tone="sky" icon="x" ariaLabel="t" label="Photos" count={3} onOpen={open} />);
    fireEvent.click(screen.getByLabelText('t'));
    expect(open).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('t-count')).toHaveTextContent('3');
    expect(screen.getByLabelText('t-count').className).toContain('pe-pill');
  });
});

describe('ProjectHub: the colour of each tile of the object (the owner\'s choice of 2026-10-18)', () => {
  it('gives each work place its own colour, the estimate stays amber and the summary white', () => {
    render(<I18nProvider><ProjectHub onOpenEstimates={() => {}} onOpenSection={() => {}} /></I18nProvider>);
    const tone = (label: string) => screen.getByLabelText(label).getAttribute('data-tone');
    expect(tone('open-estimates')).toBe('accent');
    expect(tone('object-tile-rooms')).toBe('green');
    expect(tone('object-tile-photos')).toBe('sky');
    expect(tone('object-tile-documents')).toBe('pink');
    expect(tone('object-tile-legal')).toBe('slate');
    expect(tone('object-tile-payments')).toBe('yellow');
    expect(tone('object-tile-summary')).toBe('white');
  });

  it('leaves only the summary of the object white', () => {
    render(<I18nProvider><ProjectHub onOpenEstimates={() => {}} onOpenSection={() => {}} /></I18nProvider>);
    expect(screen.getAllByRole('button').filter((b) => b.getAttribute('data-tone') === 'white')).toHaveLength(1);
  });
});
