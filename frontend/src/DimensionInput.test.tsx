import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DimensionInput } from './components/DimensionInput';

function Harness({ initial = '', onMeters }: { initial?: string; onMeters?: (m: string) => void }) {
  const [meters, setMeters] = useState(initial);
  return (
    <>
      <DimensionInput
        aria-label="dim"
        value={meters}
        onValueChange={(m) => {
          setMeters(m);
          onMeters?.(m);
        }}
      />
      <output aria-label="meters">{meters}</output>
      <button type="button" aria-label="prefill" onClick={() => setMeters('2.700')}>prefill</button>
      <button type="button" aria-label="reset" onClick={() => setMeters('')}>reset</button>
    </>
  );
}

describe('DimensionInput (Stage 18G)', () => {
  it('takes centimetres and hands the form metres', () => {
    const onMeters = vi.fn();
    render(<Harness onMeters={onMeters} />);
    fireEvent.change(screen.getByLabelText('dim'), { target: { value: '250' } });
    expect(onMeters).toHaveBeenLastCalledWith('2.5');
    expect(screen.getByLabelText('meters')).toHaveTextContent('2.5');
    expect(screen.getByLabelText('dim')).toHaveValue('250');
  });

  it('shows the metres of the form as centimetres', () => {
    render(<Harness initial="2.680" />);
    expect(screen.getByLabelText('dim')).toHaveValue('268');
  });

  it('keeps what is being typed (a lone point, a comma) and does not jump while typing', () => {
    render(<Harness />);
    const input = screen.getByLabelText('dim');
    fireEvent.change(input, { target: { value: '25.' } });
    expect(input).toHaveValue('25.');
    fireEvent.change(input, { target: { value: '25,5' } });
    expect(input).toHaveValue('25.5');
    expect(screen.getByLabelText('meters')).toHaveTextContent('0.255');
    fireEvent.change(input, { target: { value: '25.55' } });
    expect(input).toHaveValue('25.5');
  });

  it('follows a change the form makes itself (a prefill, a reset)', () => {
    render(<Harness initial="1" />);
    fireEvent.click(screen.getByLabelText('prefill'));
    expect(screen.getByLabelText('dim')).toHaveValue('270');
    fireEvent.click(screen.getByLabelText('reset'));
    expect(screen.getByLabelText('dim')).toHaveValue('');
  });

  it('is a text field with the decimal keypad', () => {
    render(<Harness />);
    expect(screen.getByLabelText('dim')).toHaveAttribute('type', 'text');
    expect(screen.getByLabelText('dim')).toHaveAttribute('inputMode', 'decimal');
  });

  it('hands a non-number back as it is, so the form refuses it instead of reading it as zero', () => {
    const onMeters = vi.fn();
    render(<Harness onMeters={onMeters} />);
    fireEvent.change(screen.getByLabelText('dim'), { target: { value: 'abc' } });
    expect(onMeters).toHaveBeenLastCalledWith('abc');
  });
});
