import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { BottomNav } from './BottomNav';
import { SurfaceRowButton } from './SurfaceRowButton';

// owner 2026-10-31 (item 9): a screen reader reads a readable name; the technical aria-label stays for the tests and the scripts
describe('readable names for a screen reader', () => {
  it('names a wall row by its name, badges and area, and its pencil by the action and the wall', () => {
    render(
      <I18nProvider>
        <SurfaceRowButton
          surfaceId={null}
          rowKey="w1"
          name="Ściana 1"
          area="12,50 m²"
          workCount={3}
          riskCount={2}
          className=""
          onOpen={vi.fn()}
          onEdit={vi.fn()}
          editLabel="Zmień nazwę"
        />
      </I18nProvider>,
    );
    const row = screen.getByLabelText('surface-row-w1');
    expect(row).toHaveAccessibleName(/^Ściana 1, .*2.*, .*3, 12,50 m²$/);
    expect(screen.getByLabelText('edit-surface-w1')).toHaveAccessibleName('Zmień nazwę: Ściana 1');
    // the name adds no text to the page
    expect(row).toHaveTextContent(/^Ściana 1/);
    expect(screen.queryAllByText(/Ściana 1,/)).toHaveLength(0);
  });

  it('names the bottom bar by its visible labels', () => {
    render(
      <I18nProvider>
        <BottomNav active="projects" onSelect={vi.fn()} onMore={vi.fn()} />
      </I18nProvider>,
    );
    expect(screen.getByLabelText('bottom-nav-projects')).toHaveAccessibleName('Obiekty');
    expect(screen.getByLabelText('bottom-nav-more')).not.toHaveAccessibleName('bottom-nav-more');
    for (const id of ['clients', 'pricebook', 'more']) {
      expect(screen.getByLabelText(`bottom-nav-${id}`).getAttribute('aria-labelledby')).toBe(`pe-name-bottom-nav-${id}`);
    }
  });
});
