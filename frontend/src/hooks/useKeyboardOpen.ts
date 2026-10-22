import { useEffect, useState } from 'react';

/**
 * True while the on-screen keyboard is probably open (usability U-11): the visual viewport is much shorter than the window, or a text
 * field has the focus. The bottom bar hides then, so it never covers a field being typed in.
 */
export function useKeyboardOpen(): boolean {
  const [shrunk, setShrunk] = useState(false);
  const [typing, setTyping] = useState(false);

  useEffect(() => {
    const viewport = window.visualViewport;
    const check = () => setShrunk(!!viewport && viewport.height < window.innerHeight * 0.75);
    viewport?.addEventListener('resize', check);
    check();
    const isField = (el: EventTarget | null) =>
      el instanceof HTMLElement && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') && !(el as HTMLInputElement).readOnly
      && !['checkbox', 'radio', 'button', 'submit', 'file'].includes((el as HTMLInputElement).type);
    const onIn = (event: FocusEvent) => setTyping(isField(event.target));
    const onOut = () => setTyping(false);
    document.addEventListener('focusin', onIn);
    document.addEventListener('focusout', onOut);
    return () => {
      viewport?.removeEventListener('resize', check);
      document.removeEventListener('focusin', onIn);
      document.removeEventListener('focusout', onOut);
    };
  }, []);

  return shrunk || typing;
}
