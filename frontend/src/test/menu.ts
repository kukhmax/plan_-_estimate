import { fireEvent, screen } from '@testing-library/react';

// The sections of the application are reached through the main menu: open it, then press the item.
export async function openMenu(): Promise<void> {
  fireEvent.click(await screen.findByRole('button', { name: 'open-menu' }));
}

export async function chooseSection(name: 'show-clients' | 'show-projects' | 'show-pricebook'): Promise<void> {
  await openMenu();
  fireEvent.click(screen.getByRole('button', { name }));
}

export async function openAccountDialog(): Promise<void> {
  await openMenu();
  fireEvent.click(screen.getByRole('button', { name: 'open-account' }));
}
