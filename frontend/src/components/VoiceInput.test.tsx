import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../hooks/useI18n';
import { VoiceInput } from './VoiceInput';

// V2-V — the microphone beside a numeric field: the recognizer of the browser where there is one, the dictation of the keyboard of the phone where there is not.

interface Fake {
  lang: string;
  stopped: boolean;
  aborted: boolean;
  onresult: ((event: unknown) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}
let recognizers: Fake[] = [];

class FakeRecognition implements Fake {
  lang = '';
  interimResults = false;
  continuous = true;
  maxAlternatives = 1;
  stopped = false;
  aborted = false;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  constructor() {
    recognizers.push(this);
  }
  start() {}
  stop() {
    this.stopped = true;
    this.onend?.();
  }
  abort() {
    this.aborted = true;
  }
}

const heard = (rec: Fake, alternatives: string[], isFinal = true) =>
  act(() => {
    rec.onresult?.({ resultIndex: 0, results: [Object.assign(alternatives.map((transcript) => ({ transcript })), { isFinal })] });
  });
const finish = (rec: Fake) => act(() => rec.onend?.());

function renderField(props: Partial<React.ComponentProps<typeof VoiceInput>> = {}, locale = 'pl') {
  localStorage.setItem('locale', locale);
  const onValue = vi.fn();
  render(
    <I18nProvider>
      <VoiceInput name="amount" mode="plain" onValue={onValue} {...props}>
        <input aria-label="the-field" className="flex-1 min-w-0" />
      </VoiceInput>
    </I18nProvider>,
  );
  return onValue;
}
const mic = () => screen.getByLabelText('voice-amount');

function withRecognizer() {
  (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
}
function withoutRecognizer() {
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  delete (window as unknown as Record<string, unknown>).SpeechRecognition;
}

beforeEach(() => {
  recognizers = [];
  localStorage.clear();
  withoutRecognizer();
});
afterEach(() => {
  cleanup();
  withoutRecognizer();
});

describe('the microphone', () => {
  it('stands beside the field, is touch-sized and has a name', () => {
    renderField();
    expect(mic().className).toContain('min-h-11');
    expect(mic().className).toContain('min-w-11');
    expect(mic()).toHaveAttribute('aria-pressed', 'false');
    expect(mic()).toHaveTextContent('Powiedz liczbę (mikrofon)');
    expect(screen.getByLabelText('the-field')).toBeInTheDocument();
  });

  it('does nothing when disabled', () => {
    renderField({ disabled: true });
    expect(mic()).toBeDisabled();
  });
});

describe('with the recognizer of the browser', () => {
  beforeEach(withRecognizer);

  it('listens in the language of the screen, shows what it hears, and types the number it understood', () => {
    const onValue = renderField();
    fireEvent.click(mic());
    expect(recognizers).toHaveLength(1);
    expect(recognizers[0].lang).toBe('pl-PL');
    expect(mic()).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('voice-status-amount')).toHaveTextContent('Słucham… powiedz liczbę');
    heard(recognizers[0], ['pięć przecinek'], false);
    expect(screen.getByLabelText('voice-status-amount')).toHaveTextContent('«pięć przecinek»');
    heard(recognizers[0], ['pięć przecinek dwa', 'pięć przecinek dwa zł']);
    finish(recognizers[0]);
    expect(onValue).toHaveBeenCalledWith('5.2');
    expect(screen.getByLabelText('voice-status-amount')).toHaveTextContent('Usłyszano „pięć przecinek dwa” → 5,2');
    expect(mic()).toHaveAttribute('aria-pressed', 'false');
  });

  it('takes the first alternative that is a number', () => {
    const onValue = renderField();
    fireEvent.click(mic());
    heard(recognizers[0], ['piąty raz', 'sto dwadzieścia pięć', 'sto']);
    finish(recognizers[0]);
    expect(onValue).toHaveBeenCalledTimes(1);
    expect(onValue).toHaveBeenCalledWith('125');
  });

  it('says what the number became for a length field (the field is in centimetres) and gives metres', () => {
    const onValue = renderField({ mode: 'length', show: (value) => `${Math.round(Number(value) * 100)} cm` });
    fireEvent.click(mic());
    heard(recognizers[0], ['trzy metry osiemdziesiąt']);
    finish(recognizers[0]);
    expect(onValue).toHaveBeenCalledWith('3.8');
    expect(screen.getByLabelText('voice-status-amount')).toHaveTextContent('→ 380 cm');
  });

  it('stops when the button is tapped again', () => {
    renderField();
    fireEvent.click(mic());
    fireEvent.click(mic());
    expect(recognizers[0].stopped).toBe(true);
    expect(mic()).toHaveAttribute('aria-pressed', 'false');
  });

  it('does not touch the field when the words are not a number, and says so', () => {
    const onValue = renderField();
    fireEvent.click(mic());
    heard(recognizers[0], ['dzień dobry']);
    finish(recognizers[0]);
    expect(onValue).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Nie zrozumiałem „dzień dobry”');
  });

  it.each([
    ['no-speech', 'Nic nie słychać'],
    ['not-allowed', 'Brak zgody na mikrofon'],
    ['audio-capture', 'Nie znaleziono mikrofonu'],
    ['network', 'Rozpoznawanie mowy jest tu niedostępne'],
    ['service-not-allowed', 'Rozpoznawanie mowy jest tu niedostępne'],
  ])('answers the browser error "%s" in words, with the way out through the keyboard', (code, words) => {
    const onValue = renderField();
    fireEvent.click(mic());
    act(() => recognizers[0].onerror?.({ error: code }));
    finish(recognizers[0]);
    expect(screen.getByRole('alert')).toHaveTextContent(words);
    expect(onValue).not.toHaveBeenCalled();
    const keyboard = screen.getByLabelText('voice-keyboard-amount');
    expect(keyboard.className).toContain('min-h-11');
    fireEvent.click(keyboard);
    expect(screen.getByLabelText('voice-panel-amount')).toBeInTheDocument();
  });

  it('keeps quiet about a recognizer that was cancelled on purpose', () => {
    renderField();
    fireEvent.click(mic());
    act(() => recognizers[0].onerror?.({ error: 'aborted' }));
    finish(recognizers[0]);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('lets the owner choose the language of the speech, remembers it and uses it the next time', () => {
    renderField();
    fireEvent.click(mic());
    heard(recognizers[0], ['pięć']);
    finish(recognizers[0]);
    const select = screen.getByLabelText('voice-lang-amount') as HTMLSelectElement;
    expect(select.className).toContain('min-h-11');
    expect([...select.options].map((o) => o.textContent)).toEqual(['Polski', 'Русский', 'Українська', 'English']);
    fireEvent.change(select, { target: { value: 'ru' } });
    expect(localStorage.getItem('speech_lang')).toBe('ru');
    fireEvent.click(mic());
    expect(recognizers[1].lang).toBe('ru-RU');
    cleanup();
    recognizers = [];
    renderField({}, 'en'); // a new screen: the chosen language still wins over the language of the screen
    fireEvent.click(mic());
    expect(recognizers[0].lang).toBe('ru-RU');
  });

  it('takes the language of the screen when none was chosen', () => {
    renderField({}, 'uk');
    fireEvent.click(mic());
    expect(recognizers[0].lang).toBe('uk-UA');
  });

  it('cancels the recognizer when the screen goes away', () => {
    renderField();
    fireEvent.click(mic());
    cleanup();
    expect(recognizers[0].aborted).toBe(true);
  });
});

describe('without the recognizer of the browser: the dictation of the keyboard', () => {
  it('opens a small panel with a field, an example and no language switch', () => {
    renderField();
    fireEvent.click(mic());
    const panel = screen.getByLabelText('voice-panel-amount');
    expect(panel).toHaveTextContent('Podyktuj liczbę');
    expect(panel).toHaveTextContent('Naciśnij mikrofon na klawiaturze telefonu');
    expect(panel).toHaveTextContent('„pięć przecinek dwa”');
    expect(screen.getByLabelText('voice-text-amount')).toHaveFocus();
    expect(screen.queryByLabelText('voice-lang-amount')).toBeNull();
    for (const name of ['voice-insert-amount', 'voice-close-amount']) {
      expect(screen.getByLabelText(name).className).toContain('min-h-11');
      expect(screen.getByLabelText(name).className).toContain('w-full');
    }
  });

  it('shows the number it understands as it is typed, inserts it and closes', () => {
    const onValue = renderField();
    fireEvent.click(mic());
    expect(screen.getByLabelText('voice-insert-amount')).toBeDisabled();
    expect(screen.getByLabelText('voice-preview-amount')).toHaveTextContent('Nie rozumiem jeszcze liczby.');
    fireEvent.change(screen.getByLabelText('voice-text-amount'), { target: { value: 'сто двадцать пять и пять' } });
    expect(screen.getByLabelText('voice-preview-amount')).toHaveTextContent('→ 125,5');
    fireEvent.click(screen.getByLabelText('voice-insert-amount'));
    expect(onValue).toHaveBeenCalledWith('125.5');
    expect(screen.queryByLabelText('voice-panel-amount')).toBeNull();
    expect(screen.getByLabelText('voice-status-amount')).toHaveTextContent('Usłyszano „сто двадцать пять и пять” → 125,5');
  });

  it('inserts with Enter and understands every language in any screen', () => {
    const onValue = renderField({}, 'en');
    fireEvent.click(mic());
    const field = screen.getByLabelText('voice-text-amount');
    fireEvent.change(field, { target: { value: 'pięć przecinek dwa' } });
    fireEvent.keyDown(field, { key: 'Enter' });
    expect(onValue).toHaveBeenCalledWith('5.2');
  });

  it('does not insert what is not a number, and closes without a change', () => {
    const onValue = renderField();
    fireEvent.click(mic());
    fireEvent.change(screen.getByLabelText('voice-text-amount'), { target: { value: 'dzień dobry' } });
    fireEvent.keyDown(screen.getByLabelText('voice-text-amount'), { key: 'Enter' });
    expect(onValue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('voice-close-amount'));
    expect(screen.queryByLabelText('voice-panel-amount')).toBeNull();
    expect(onValue).not.toHaveBeenCalled();
  });

  it('shows the examples of a length field and its number in centimetres', () => {
    const onValue = renderField({ mode: 'length', show: (value) => `${Math.round(Number(value) * 100)} cm` });
    fireEvent.click(mic());
    expect(screen.getByLabelText('voice-panel-amount')).toHaveTextContent('„trzy metry osiemdziesiąt”');
    fireEvent.change(screen.getByLabelText('voice-text-amount'), { target: { value: 'два пятьдесят' } });
    expect(screen.getByLabelText('voice-preview-amount')).toHaveTextContent('→ 250 cm');
    fireEvent.click(screen.getByLabelText('voice-insert-amount'));
    expect(onValue).toHaveBeenCalledWith('2.50');
  });

  it('closes the panel with a second tap on the microphone', () => {
    renderField();
    fireEvent.click(mic());
    fireEvent.click(mic());
    expect(screen.queryByLabelText('voice-panel-amount')).toBeNull();
  });

  it('speaks Russian, Ukrainian and English', () => {
    for (const [locale, title, none] of [
      ['ru', 'Продиктуйте число', 'Число пока не распознано.'],
      ['uk', 'Продиктуйте число', 'Число поки не розпізнано.'],
      ['en', 'Dictate the number', 'No number understood yet.'],
    ] as const) {
      renderField({}, locale);
      fireEvent.click(mic());
      expect(screen.getByLabelText('voice-panel-amount')).toHaveTextContent(title);
      expect(screen.getByLabelText('voice-preview-amount')).toHaveTextContent(none);
      cleanup();
    }
  });
});
