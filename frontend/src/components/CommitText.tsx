import { useEffect, useState } from 'react';

export const FIELD = 'w-full min-h-11 border border-slate-200 rounded-lg px-3 py-2 text-base bg-white text-slate-900';

/** A text field that keeps what is typed and saves it when the field is left (one request per field, not per letter). */
export function CommitText({
  label, value, onCommit, multiline = false, inputMode, type = 'text',
}: {
  label: string;
  value: string;
  onCommit: (text: string) => void;
  multiline?: boolean;
  inputMode?: 'decimal' | 'numeric' | 'text';
  type?: string;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const commit = () => {
    if (text !== value && !(text.trim() === '' && value.trim() === '')) onCommit(text);  // a blank over a blank is no change
  };
  return multiline ? (
    <textarea aria-label={label} value={text} rows={2} onChange={(e) => setText(e.target.value)} onBlur={commit} className={FIELD} />
  ) : (
    <input aria-label={label} type={type} inputMode={inputMode} value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} className={FIELD} />
  );
}
