import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { PhotoEntryButton } from './PhotoEntryButton';

function renderButton(props: Partial<React.ComponentProps<typeof PhotoEntryButton>> = {}) {
  const onToggle = vi.fn();
  render(
    <I18nProvider>
      <PhotoEntryButton count={3} expanded={false} onToggle={onToggle} {...props} />
    </I18nProvider>,
  );
  return { onToggle };
}

describe('PhotoEntryButton (corner button, C-1)', () => {
  beforeEach(() => localStorage.clear());

  it('shows the count and a localized accessible name (PL)', () => {
    renderButton();
    const button = screen.getByRole('button', { name: 'Zdjęcia: 3' });
    expect(button).toHaveTextContent('3');
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('is localized in Russian', () => {
    localStorage.setItem('locale', 'ru');
    renderButton({ count: 12 });
    expect(screen.getByRole('button', { name: 'Фото: 12' })).toHaveTextContent('12');
  });

  it('reports its expanded state and toggles on tap', () => {
    const { onToggle } = renderButton({ expanded: true });
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('keeps a ≥ 44 px touch target and never shrinks inside a header (mobile rules)', () => {
    renderButton({ count: 0 });
    const button = screen.getByRole('button');
    expect(button).toHaveClass('min-h-11', 'min-w-11', 'shrink-0');
  });

  it('uses theme tokens only, so dark mode needs no extra rules', () => {
    renderButton();
    const html = screen.getByRole('button').outerHTML;
    expect(html).toContain('var(--tg-');
    expect(html).not.toMatch(/bg-white|text-slate|border-slate/);
  });
});
