import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SurfaceDimensions } from './components/SurfaceDimensions';
import { I18nProvider } from './hooks/useI18n';

const view = (onSave: (w: number, h: number) => Promise<void> = vi.fn(async () => undefined), props: Partial<React.ComponentProps<typeof SurfaceDimensions>> = {}) =>
  render(
    <I18nProvider>
      <SurfaceDimensions surfaceId="w1" width={1.95} height={2.6} onSave={onSave} {...props} />
    </I18nProvider>,
  );

describe('SurfaceDimensions (Stage 19, owner request)', () => {
  beforeEach(() => localStorage.clear());

  it('closes the fields by itself once the size is saved, and not before', async () => {
    let finish: () => void = () => undefined;
    const onSave = vi.fn((_w: number, _h: number) => new Promise<void>((resolve) => (finish = resolve)));
    view(onSave);
    fireEvent.click(screen.getByLabelText('edit-dimensions-w1'));
    fireEvent.change(screen.getByLabelText('dimensions-width-w1'), { target: { value: '200' } });
    fireEvent.click(screen.getByLabelText('dimensions-save-w1'));

    expect(onSave).toHaveBeenCalledWith(2, 2.6);
    expect(screen.getByLabelText('dimensions-form-w1')).toBeInTheDocument(); // still open while it is being saved
    expect(screen.getByLabelText('dimensions-save-w1')).toBeDisabled();
    expect(screen.getByLabelText('dimensions-cancel-w1')).toBeDisabled();
    finish();
    await waitFor(() => expect(screen.queryByLabelText('dimensions-form-w1')).toBeNull());
    expect(screen.getByLabelText('edit-dimensions-w1')).toBeInTheDocument();
  });

  it('opens with what is saved each time, not with what was typed and cancelled before', () => {
    view();
    fireEvent.click(screen.getByLabelText('edit-dimensions-w1'));
    fireEvent.change(screen.getByLabelText('dimensions-width-w1'), { target: { value: '999' } });
    fireEvent.click(screen.getByLabelText('dimensions-cancel-w1'));
    fireEvent.click(screen.getByLabelText('edit-dimensions-w1'));
    expect(screen.getByLabelText('dimensions-width-w1')).toHaveValue('195');
  });

  it('a stale error is gone when it is opened again', async () => {
    view(vi.fn(async () => { throw new Error('nope'); }));
    fireEvent.click(screen.getByLabelText('edit-dimensions-w1'));
    fireEvent.click(screen.getByLabelText('dimensions-save-w1'));
    expect(await screen.findByText('nope')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('dimensions-cancel-w1'));
    fireEvent.click(screen.getByLabelText('edit-dimensions-w1'));
    expect(screen.queryByText('nope')).toBeNull();
  });
});
