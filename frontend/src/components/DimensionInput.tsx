import { useEffect, useRef, useState, type InputHTMLAttributes } from 'react';
import { cmToMeters, metersToCm, sanitizeCm } from '../utils/dimensions';

interface DimensionInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type' | 'inputMode'> {
  /** The dimension in METRES as text ("2.5"); the field shows and takes centimetres. */
  value: string;
  onValueChange: (meters: string) => void;
}

/**
 * A field for a length typed in centimetres ("250" is 2.5 m) so the owner never types the decimal point on site.
 * The form above keeps working in metres: it gets the metres text through `onValueChange` and hands the metres text back through `value`.
 */
export function DimensionInput({ value, onValueChange, ...rest }: DimensionInputProps) {
  const [text, setText] = useState(() => metersToCm(value));
  const emitted = useRef(value);

  // the form changed the value itself (a prefill, a reset): show it; the value we sent a moment ago is not a change
  useEffect(() => {
    if (value !== emitted.current) {
      emitted.current = value;
      setText(metersToCm(value));
    }
  }, [value]);

  return (
    <input
      {...rest}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={text}
      onChange={(event) => {
        const typed = sanitizeCm(event.target.value);
        setText(typed);
        const meters = cmToMeters(typed);
        emitted.current = meters;
        onValueChange(meters);
      }}
    />
  );
}
