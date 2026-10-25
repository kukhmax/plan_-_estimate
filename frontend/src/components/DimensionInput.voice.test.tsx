import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { DimensionInput } from './DimensionInput';

// V2-V — the microphone of a size: what is said is metres for the form above and centimetres in the field.

function Harness({ onMeters, voice }: { onMeters: (value: string) => void; voice?: boolean }) {
  const [meters, setMeters] = useState('');
  return (
    <I18nProvider>
      <DimensionInput
        aria-label="room-width"
        value={meters}
        voice={voice}
        onValueChange={(value) => {
          setMeters(value);
          onMeters(value);
        }}
      />
    </I18nProvider>
  );
}
afterEach(cleanup);

describe('DimensionInput with the microphone', () => {
  it('has a microphone, and the typing of centimetres is as it was', () => {
    const onMeters = vi.fn();
    render(<Harness onMeters={onMeters} />);
    expect(screen.getByLabelText('voice-room-width')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('room-width'), { target: { value: '250' } });
    expect(onMeters).toHaveBeenLastCalledWith('2.5');
    expect((screen.getByLabelText('room-width') as HTMLInputElement).value).toBe('250');
  });

  it.each([
    ['два пятьдесят', '250', '2.5'],
    ['три метра восемьдесят', '380', '3.8'],
    ['trzy metry osiemdziesiąt', '380', '3.8'],
    ['двести пятьдесят', '250', '2.5'],
    ['250 cm', '250', '2.5'],
    ['five point two', '520', '5.2'],
    ['два', '200', '2'],
  ])('"%s" is %s cm in the field and %s m for the form', (spoken, shown, meters) => {
    const onMeters = vi.fn();
    render(<Harness onMeters={onMeters} />);
    fireEvent.click(screen.getByLabelText('voice-room-width'));
    fireEvent.change(screen.getByLabelText('voice-text-room-width'), { target: { value: spoken } });
    expect(screen.getByLabelText('voice-preview-room-width')).toHaveTextContent(`→ ${shown} cm`);
    fireEvent.click(screen.getByLabelText('voice-insert-room-width'));
    expect(onMeters).toHaveBeenLastCalledWith(meters);
    expect((screen.getByLabelText('room-width') as HTMLInputElement).value).toBe(shown);
  });

  it('keeps the field when the words are no size', () => {
    const onMeters = vi.fn();
    render(<Harness onMeters={onMeters} />);
    fireEvent.change(screen.getByLabelText('room-width'), { target: { value: '300' } });
    fireEvent.click(screen.getByLabelText('voice-room-width'));
    fireEvent.change(screen.getByLabelText('voice-text-room-width'), { target: { value: 'dzień dobry' } });
    expect(screen.getByLabelText('voice-insert-room-width')).toBeDisabled();
    expect((screen.getByLabelText('room-width') as HTMLInputElement).value).toBe('300');
  });

  it('can be a field without the microphone', () => {
    render(<Harness onMeters={vi.fn()} voice={false} />);
    expect(screen.queryByLabelText('voice-room-width')).toBeNull();
    expect(screen.getByLabelText('room-width')).toBeInTheDocument();
  });
});
