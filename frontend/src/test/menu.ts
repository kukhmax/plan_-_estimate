import { fireEvent, screen } from '@testing-library/react';

// The sections of the application are reached through the main menu: open it, then press the item.
export async function openMenu(): Promise<void> {
  fireEvent.click(await screen.findByRole('button', { name: 'open-menu' }));
}

export async function chooseSection(name: 'show-clients' | 'show-projects' | 'show-calendar' | 'show-pricebook' | 'show-archive' | 'show-documents' | 'show-knowledge' | 'show-access' | 'show-security'): Promise<void> {
  await openMenu();
  fireEvent.click(screen.getByRole('button', { name }));
}

export async function openAccountDialog(): Promise<void> {
  await openMenu();
  fireEvent.click(screen.getByRole('button', { name: 'open-account' }));
}

// Usability U-4: the coefficient, the break and the removal of a planned work are in the menu of its row ("⋯"); open the menus first.
export function openOccurrenceMenus(scope: HTMLElement | Document = document): void {
  scope.querySelectorAll<HTMLButtonElement>('button[aria-label^="occurrence-menu-"][aria-expanded="false"]').forEach((button) => fireEvent.click(button));
}

/** Opens the menu of ONE work row (by its draft key) and returns nothing: the action buttons of the row are then in the document. */
export function openOccurrenceMenu(draftKey: string): void {
  const button = document.querySelector<HTMLButtonElement>(`button[aria-label="occurrence-menu-${draftKey}"]`);
  if (button && button.getAttribute('aria-expanded') === 'false') fireEvent.click(button);
}
