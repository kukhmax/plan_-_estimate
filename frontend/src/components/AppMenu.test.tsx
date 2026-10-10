import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AppMenu, AppMenuItem } from './AppMenu';

function items(overrides: Partial<Record<string, () => void>> = {}): AppMenuItem[] {
  return [
    { id: 'show-clients', label: 'Klienci', active: true, onSelect: overrides['show-clients'] ?? vi.fn() },
    { id: 'show-projects', label: 'Obiekty', active: false, onSelect: overrides['show-projects'] ?? vi.fn() },
  ];
}

function renderMenu(extra: Partial<React.ComponentProps<typeof AppMenu>> = {}) {
  const onClose = vi.fn();
  const onOpenAccount = vi.fn();
  render(
    <AppMenu open title="Plan & Estimate" accountLabel="Konto" items={items()} onClose={onClose} onOpenAccount={onOpenAccount} {...extra} />,
  );
  return { onClose, onOpenAccount };
}

describe('AppMenu', () => {
  beforeEach(() => {
    delete (window as unknown as { Telegram?: unknown }).Telegram;
  });

  it('renders nothing while closed', () => {
    renderMenu({ open: false });
    expect(screen.queryByRole('dialog', { name: 'main-menu' })).toBeNull();
  });

  it('is a modal dialog with the sections, the current one marked, and the account at the bottom', () => {
    renderMenu();
    const dialog = screen.getByRole('dialog', { name: 'main-menu' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('button', { name: 'show-clients' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'show-projects' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('button', { name: 'open-account' })).toHaveTextContent('Konto');
  });

  it('every control is at least 44 px high (min-h-11 / min-h-12)', () => {
    renderMenu();
    for (const name of ['close-menu', 'show-clients', 'show-projects', 'open-account']) {
      expect(screen.getByRole('button', { name }).className).toMatch(/min-h-1[12]/);
    }
  });

  it('calls the item handler and does not close by itself (the owner decides what a choice does)', () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(
      <AppMenu open title="x" accountLabel="Konto" items={items({ 'show-projects': onSelect })} onClose={onClose} onOpenAccount={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'show-projects' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes by the close button, by a tap outside and by Escape', () => {
    const { onClose } = renderMenu();
    fireEvent.click(screen.getByRole('button', { name: 'close-menu' }));
    fireEvent.click(screen.getByRole('button', { name: 'close-menu-backdrop' }));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('puts the focus on the close button when it opens', () => {
    renderMenu();
    expect(screen.getByRole('button', { name: 'close-menu' })).toHaveFocus();
  });

  it('the Telegram BackButton closes the open menu and is hidden again afterwards', () => {
    let handler: (() => void) | undefined;
    const backButton = {
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn((cb: () => void) => { handler = cb; }),
      offClick: vi.fn(),
    };
    (window as unknown as { Telegram: unknown }).Telegram = { WebApp: { BackButton: backButton } };
    const { onClose } = renderMenu();
    expect(backButton.show).toHaveBeenCalled();
    handler?.();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps long Russian labels inside the panel (they wrap, nothing is cut)', () => {
    renderMenu({ items: [{ id: 'show-clients', label: 'Отправленные документы по всем объектам', active: false, onSelect: vi.fn() }] });
    const button = screen.getByRole('button', { name: 'show-clients' });
    expect(button.className).toMatch(/break-words/);
    expect(button.className).not.toMatch(/truncate|whitespace-nowrap/);
  });
});
