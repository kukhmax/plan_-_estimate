/**
 * The speech recognizer the browser has (V2-V): the Web Speech API. The application calls no service of its own and keeps no sound; where the browser has no
 * recognizer (many Telegram WebViews) the screen uses the dictation of the keyboard of the phone instead (`VoiceInput`).
 */
import { LOCALE_TAGS, isLocale, type Locale } from './locale';

export const SPEECH_LANGS = ['pl', 'ru', 'uk', 'en'] as const;
export type SpeechLang = Locale;

const STORAGE_KEY = 'speech_lang';

interface RecognitionEventLike {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
  resultIndex: number;
}
interface RecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((event: RecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type RecognitionCtor = new () => RecognitionLike;

function ctorOf(win: Window): RecognitionCtor | null {
  const holder = win as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return holder.SpeechRecognition ?? holder.webkitSpeechRecognition ?? null;
}

/** Whether this browser has a speech recognizer at all. */
export function speechRecognitionSupported(win: Window = window): boolean {
  return ctorOf(win) !== null;
}

/** The language of the speech: the one the owner chose before, else the language of the screens. */
export function loadSpeechLang(fallback: Locale): SpeechLang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isLocale(stored)) return stored;
  } catch {
    // no storage (a private window): the language of the screens
  }
  return fallback;
}

export function saveSpeechLang(lang: SpeechLang): void {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // not remembered: it is only a convenience
  }
}

export interface ListenHandlers {
  /** What was heard so far (`final` once the phrase is complete); the first of the alternatives is the recognizer's favourite. */
  onHeard: (alternatives: string[], final: boolean) => void;
  /** The code of the browser ("not-allowed", "no-speech", "audio-capture", "network", "service-not-allowed", ...). */
  onError: (code: string) => void;
  onEnd: () => void;
}

export interface Listening {
  stop: () => void;
  abort: () => void;
}

/** Starts listening; throws when there is no recognizer (check `speechRecognitionSupported` first). */
export function listen(lang: SpeechLang, handlers: ListenHandlers, win: Window = window): Listening {
  const Ctor = ctorOf(win);
  if (!Ctor) throw new Error('speech recognition is not available');
  const recognition = new Ctor();
  recognition.lang = LOCALE_TAGS[lang];
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 5;
  recognition.onresult = (event) => {
    const last = event.results[event.results.length - 1];
    if (!last) return;
    const alternatives: string[] = [];
    for (let i = 0; i < last.length; i += 1) alternatives.push(last[i].transcript);
    handlers.onHeard(alternatives, last.isFinal);
  };
  recognition.onerror = (event) => handlers.onError(event.error ?? 'unknown');
  recognition.onend = () => handlers.onEnd();
  recognition.start();
  return { stop: () => recognition.stop(), abort: () => recognition.abort() };
}
