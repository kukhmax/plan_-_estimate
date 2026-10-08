import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoBackContext } from '../hooks/PhotoBackContext';
import { I18nProvider } from '../hooks/useI18n';
import { makeMarker } from '../test/photoFixtures';
import { PointMarkerPopup } from './PointMarkerPopup';

const ATT = 'b0000000-0000-4000-8000-000000000001';

function renderPopup(over: Partial<React.ComponentProps<typeof PointMarkerPopup>> = {}, registry: { register: (close: () => void) => () => void } | null = null) {
  const handlers = { onSaveLabel: vi.fn(), onDelete: vi.fn(), onClose: vi.fn() };
  const marker = over.marker ?? makeMarker(ATT, { label: 'rysa przy oknie' });
  const view = render(
    <I18nProvider>
      <PhotoBackContext.Provider value={registry}>
        <PointMarkerPopup marker={marker} number={3} readOnly={false} busy={false} error={null} {...handlers} {...over} />
      </PhotoBackContext.Provider>
    </I18nProvider>,
  );
  return { ...handlers, marker, ...view };
}

describe('PointMarkerPopup', () => {
  beforeEach(() => localStorage.clear());

  it('is a dialog named after the marker number and shows the label in an input', () => {
    renderPopup();
    expect(screen.getByRole('dialog', { name: 'Znacznik 3' })).toBeInTheDocument();
    expect(screen.getByLabelText('Podpis znacznika')).toHaveValue('rysa przy oknie');
  });

  it('the label input is 40 characters at most, 16 px (no zoom on focus) and counts the characters', () => {
    renderPopup();
    const input = screen.getByLabelText('Podpis znacznika');
    expect(input).toHaveAttribute('maxlength', '40');
    expect(input).toHaveClass('text-base', 'min-h-11');
    expect(screen.getByText('15 / 40')).toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'abc' } });
    expect(screen.getByText('3 / 40')).toBeInTheDocument();
  });

  it('saving is only possible after a change and sends the trimmed label', () => {
    const { onSaveLabel } = renderPopup();
    const save = screen.getByRole('button', { name: 'Zapisz podpis' });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Podpis znacznika'), { target: { value: '  pęknięcie  ' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    expect(onSaveLabel).toHaveBeenCalledWith('pęknięcie');
  });

  it('an emptied label is saved as no label (null)', () => {
    const { onSaveLabel } = renderPopup();
    fireEvent.change(screen.getByLabelText('Podpis znacznika'), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz podpis' }));
    expect(onSaveLabel).toHaveBeenCalledWith(null);
  });

  it('deletes and closes through their own buttons', () => {
    const { onDelete, onClose } = renderPopup();
    fireEvent.click(screen.getByRole('button', { name: 'Usuń znacznik' }));
    expect(onDelete).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on the backdrop and on Escape, but not on a tap inside the sheet', () => {
    const { onClose } = renderPopup();
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('dialog').parentElement!);
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('Escape is not passed on to the viewer under the pop-up', () => {
    const below = vi.fn();
    document.addEventListener('keydown', below);
    renderPopup();
    fireEvent.keyDown(document, { key: 'Escape' });
    document.removeEventListener('keydown', below);
    expect(below).not.toHaveBeenCalled();
  });

  it("Telegram's BackButton closes it first (it registers on the back stack)", () => {
    const close = vi.fn();
    let registered: (() => void) | null = null;
    const { onClose } = renderPopup({}, { register: (fn) => { registered = fn; return close; } });
    registered!();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('while busy nothing can be pressed or typed', () => {
    renderPopup({ busy: true });
    expect(screen.getByLabelText('Podpis znacznika')).toBeDisabled();
    for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
  });

  it('shows the error in the pop-up, localized by key', () => {
    renderPopup({ error: 'marker_not_found' });
    expect(screen.getByRole('alert')).toHaveTextContent('Tego znacznika już nie ma.');
  });

  it('read only (an archived photo): the label as text, no input, no save, no delete — only closing', () => {
    renderPopup({ readOnly: true });
    expect(screen.getByTestId('marker-label-text')).toHaveTextContent('rysa przy oknie');
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Zapisz podpis' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Usuń znacznik' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Zamknij' })).toBeInTheDocument();
  });

  it('read only without a label says so', () => {
    renderPopup({ readOnly: true, marker: makeMarker(ATT) });
    expect(screen.getByTestId('marker-label-text')).toHaveTextContent('Bez podpisu');
  });

  it('mobile: every control is at least 44 px high, full width, stacked; the sheet scrolls instead of overflowing', () => {
    renderPopup();
    for (const button of screen.getAllByRole('button')) expect(button).toHaveClass('min-h-11', 'w-full');
    expect(screen.getByRole('dialog')).toHaveClass('max-h-[80vh]', 'overflow-y-auto');
  });

  it('Russian labels', () => {
    localStorage.setItem('locale', 'ru');
    renderPopup();
    expect(screen.getByRole('dialog', { name: 'Метка 3' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Удалить метку' })).toBeInTheDocument();
  });
});
