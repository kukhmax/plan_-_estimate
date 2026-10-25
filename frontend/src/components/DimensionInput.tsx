import { useEffect, useRef, useState, type InputHTMLAttributes } from 'react';
import { useI18n } from '../hooks/useI18n';
import { cmToMeters, metersToCm, sanitizeCm } from '../utils/dimensions';
import { VoiceInput } from './VoiceInput';

interface DimensionInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type' | 'inputMode'> {
  /** The dimension in METRES as text ("2.5"); the field shows and takes centimetres. */
  value: string;
  onValueChange: (meters: string) => void;
  /** The microphone beside the field (V2-V): say "два пятьдесят" or "три метра восемьдесят". On by default; a field that is too narrow may turn it off. */
  voice?: boolean;
}

/**
 * A field for a length typed in centimetres ("250" is 2.5 m) so the owner never types the decimal point on site.
 * The form above keeps working in metres: it gets the metres text through `onValueChange` and hands the metres text back through `value`.
 */
export function DimensionInput({ value, onValueChange, voice = true, className, ...rest }: DimensionInputProps) {
  const { t } = useI18n();
  const [text, setText] = useState(() => metersToCm(value));
  const emitted = useRef(value);

  // the form changed the value itself (a prefill, a reset): show it; the value we sent a moment ago is not a change
  useEffect(() => {
    if (value !== emitted.current) {
      emitted.current = value;
      setText(metersToCm(value));
    }
  }, [value]);

  const field = (
    <input
      {...rest}
      className={voice ? `${className ?? ''} min-w-0 flex-1`.trim() : className}
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
  if (!voice) return field;
  return (
    <VoiceInput
      name={String(rest['aria-label'] ?? 'dimension')}
      mode="length"
      disabled={rest.disabled}
      show={(meters) => `${metersToCm(meters)} ${t.voice.cm}`}
      onValue={(spoken) => {
        // the number spoken is metres ("2.5"); the field shows centimetres and the form above keeps metres
        const shown = metersToCm(spoken);
        setText(shown);
        const meters = cmToMeters(shown);
        emitted.current = meters;
        onValueChange(meters);
      }}
    >
      {field}
    </VoiceInput>
  );
}
