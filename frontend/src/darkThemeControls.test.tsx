import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OpeningList } from './components/OpeningList';
import { I18nProvider } from './hooks/useI18n';
import {
  applyTelegramTheme,
  DEFAULT_DARK_THEME,
  DEFAULT_LIGHT_THEME,
} from './hooks/useTelegramWebApp';
import rawCss from './index.css?raw';

vi.mock('./api/openings', () => ({
  fetchOpenings: vi.fn(),
  createOpening: vi.fn(),
  updateOpening: vi.fn(),
  archiveOpening: vi.fn(),
  restoreOpening: vi.fn(),
}));

const projectId = '11111111-1111-1111-1111-111111111111';
const roomId = '22222222-2222-2222-2222-222222222222';
const surfaceId = '33333333-3333-3333-3333-333333333333';

function parseHex(hex: string): [number, number, number] {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) throw new Error(`invalid hex color "${hex}"`);
  const value = parseInt(match[1], 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function linearize(channel: number): number {
  const s = channel / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function luminance(hex: string): number {
  const [r, g, b] = parseHex(hex);
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

/** WCAG contrast ratio between two hex colors. */
function contrastBetween(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const controlVar = (property: string) =>
  document.documentElement.style.getPropertyValue(property);

afterEach(() => {
  document.documentElement.removeAttribute('style');
  document.documentElement.removeAttribute('data-color-scheme');
});

describe('dark theme form-control readability (10C.1C finding 1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('base input/select/textarea rule wins with !important over tailwind utilities', async () => {
    // The systemic rule, not the per-component utility, decides control colors.
    expect(rawCss).toContain(
      'background-color: var(--tg-control-bg-color, var(--tg-theme-secondary-bg-color)) !important',
    );
    expect(rawCss).toContain(
      'color: var(--tg-control-text-color, var(--tg-theme-text-color)) !important',
    );
    expect(rawCss).toContain(
      'border-color: var(--tg-control-border-color, var(--tg-theme-hint-color)) !important',
    );
    // Production bundle output is un-layered; the fix must not rely on @layer.
    // Source CSS still defines placeholder/focus/disabled companions.
    expect(rawCss).toMatch(/input::placeholder/);
    expect(rawCss).toMatch(/input:focus/);
    expect(rawCss).toMatch(/input:disabled/);
  });

  it('dark block defines control variables and color-scheme: dark', async () => {
    expect(rawCss).toContain("html[data-color-scheme='dark']");
    expect(rawCss).toContain('--tg-control-bg-color: #232e3c;');
    expect(rawCss).toContain('--tg-control-text-color: #f5f5f5;');
    expect(rawCss).toContain('color-scheme: dark;');
  });

  it('applying the light theme exposes light control colors and data-color-scheme=light', () => {
    applyTelegramTheme(undefined, 'light');
    expect(document.documentElement.getAttribute('data-color-scheme')).toBe('light');
    expect(controlVar('--tg-control-bg-color')).toBe('#ffffff');
    expect(controlVar('--tg-control-text-color')).toBe('#0f172a');
  });

  it('applying the dark theme exposes dark control colors and data-color-scheme=dark', () => {
    applyTelegramTheme(undefined, 'dark');
    expect(document.documentElement.getAttribute('data-color-scheme')).toBe('dark');
    expect(controlVar('--tg-control-text-color')).toBe('#f5f5f5');
    expect(controlVar('--tg-control-bg-color')).toBe('#232e3c');
    expect(controlVar('--tg-control-border-color')).toBe('#4b5f75');
  });

  it('light theme control text/bg/placeholder contrast is readable (WCAG)', () => {
    applyTelegramTheme(undefined, 'light');
    const theme = DEFAULT_LIGHT_THEME;
    expect(contrastBetween(theme['--tg-control-text-color'], theme['--tg-control-bg-color']))
      .toBeGreaterThanOrEqual(7);
    expect(contrastBetween(theme['--tg-control-placeholder-color'], theme['--tg-control-bg-color']))
      .toBeGreaterThanOrEqual(4.5);
  });

  it('dark theme control text/bg/placeholder contrast is readable (WCAG)', () => {
    applyTelegramTheme(undefined, 'dark');
    const theme = DEFAULT_DARK_THEME;
    expect(contrastBetween(theme['--tg-control-text-color'], theme['--tg-control-bg-color']))
      .toBeGreaterThanOrEqual(7);
    expect(theme['--tg-control-bg-color']).not.toBe('#ffffff');
    expect(contrastBetween(theme['--tg-control-placeholder-color'], theme['--tg-control-bg-color']))
      .toBeGreaterThanOrEqual(4.5);
  });

  it('dark control border is a distinct, defined color (field boundary visible, not white-on-white)', () => {
    applyTelegramTheme(undefined, 'dark');
    const theme = DEFAULT_DARK_THEME;
    expect(theme['--tg-control-border-color']).toMatch(/^#/);
    expect(theme['--tg-control-border-color']).not.toBe(theme['--tg-control-bg-color']);
    expect(theme['--tg-control-border-color']).not.toBe(theme['--tg-control-text-color']);
  });

  it('opening form controls render under the dark theme pipeline (jsdom; theme vars asserted, not pixels)', async () => {
    vi.mocked(await import('./api/openings')).fetchOpenings.mockResolvedValue({ items: [], total: 0 });
    applyTelegramTheme(undefined, 'dark');
    const { unmount } = render(
      <I18nProvider>
        <OpeningList projectId={projectId} roomId={roomId} surfaceId={surfaceId} />
      </I18nProvider>,
    );

    await waitFor(() => expect(screen.getByLabelText(`no-openings-${surfaceId}`)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(`add-opening-${surfaceId}`));

    expect(screen.getByLabelText('opening-width')).toBeInTheDocument();
    expect(screen.getByLabelText('opening-height')).toBeInTheDocument();
    expect(screen.getByLabelText('opening-quantity')).toBeInTheDocument();
    expect(screen.getByLabelText('opening-type')).toBeInTheDocument();
    expect(document.documentElement.getAttribute('data-color-scheme')).toBe('dark');
    expect(controlVar('--tg-control-text-color')).toBe('#f5f5f5');
    expect(controlVar('--tg-control-bg-color')).toBe('#232e3c');

    unmount();
    document.documentElement.removeAttribute('style');
    document.documentElement.removeAttribute('data-color-scheme');
    applyTelegramTheme(undefined, 'light');
    expect(document.documentElement.getAttribute('data-color-scheme')).toBe('light');
    expect(controlVar('--tg-control-text-color')).toBe('#0f172a');
  });
});