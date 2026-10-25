import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { useI18n } from '../hooks/useI18n';
import { LOCALE_NAMES } from '../utils/locale';
import { parseSpokenAlternatives, parseSpokenNumber, type SpeechMode } from '../utils/speechNumber';
import { SPEECH_LANGS, listen, loadSpeechLang, saveSpeechLang, speechRecognitionSupported, type Listening, type SpeechLang } from '../utils/speechRecognition';
import { Ico } from './Ico';

interface VoiceInputProps {
  /** A name for the technical labels of the controls: `voice-<name>`. */
  name: string;
  /** `plain`: money, hours, percent; `length`: a size, the result is in metres (see `utils/speechNumber.ts`). */
  mode: SpeechMode;
  /** Gets the number as a string with a point ("125.5"; metres for `length`). The field decides how to write it. */
  onValue: (value: string) => void;
  /** How the number is shown to the owner in "heard ... → ..." (a length field is typed in centimetres); the number with a comma by default. */
  show?: (value: string) => string;
  disabled?: boolean;
  /** Classes of the wrapper (a field inside a row of its own wants `min-w-0 flex-1`). */
  className?: string;
  /** The field itself. */
  children: ReactNode;
}

type Phase = 'idle' | 'listening' | 'dictating';
type Message = { kind: 'ok' | 'error' | 'info'; text: string };

const mic = 'shrink-0 min-h-11 min-w-11 px-3 rounded-xl border text-lg font-semibold transition disabled:opacity-50';

/**
 * V2-V — a microphone beside a numeric field: say the number, it is typed in the field. No AI and no service of ours: the browser's recognizer where there is
 * one (Web Speech), else the dictation of the keyboard of the phone through a small panel; either way the text is turned into the number by our own table of
 * words (PL / RU / UK / EN, `utils/speechNumber.ts`). What was heard and what it became are shown under the field, so a wrong word is seen and typed over.
 */
export function VoiceInput({ name, mode, onValue, show, disabled = false, className = '', children }: VoiceInputProps) {
  const { t, locale } = useI18n();
  const text = t.voice;
  const supported = speechRecognitionSupported();
  const [phase, setPhase] = useState<Phase>('idle');
  const [message, setMessage] = useState<Message | null>(null);
  const [lang, setLang] = useState<SpeechLang>(() => loadSpeechLang(locale));
  const [typed, setTyped] = useState('');
  const session = useRef<Listening | null>(null);
  const alive = useRef(true);
  const langId = useId();
  const typedId = useId();

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      session.current?.abort();
    };
  }, []);

  const shown = useCallback((value: string) => (show ? show(value) : value.replace('.', ',')), [show]);

  const accept = useCallback(
    (heard: string, value: string) => {
      onValue(value);
      setMessage({ kind: 'ok', text: text.heard.replace('{text}', heard.trim()).replace('{value}', shown(value)) });
    },
    [onValue, shown, text],
  );

  const stop = () => {
    session.current?.stop();
  };

  const start = () => {
    setMessage({ kind: 'info', text: text.listening });
    setPhase('listening');
    try {
      session.current = listen(lang, {
        onHeard: (alternatives, final) => {
          if (!alive.current) return;
          if (!final) {
            setMessage({ kind: 'info', text: `${text.listening} «${alternatives[0] ?? ''}»` });
            return;
          }
          const found = parseSpokenAlternatives(alternatives, mode);
          if (found) accept(found.text, found.value);
          else setMessage({ kind: 'error', text: text.not_understood.replace('{text}', (alternatives[0] ?? '').trim()) });
        },
        onError: (code) => {
          if (!alive.current || code === 'aborted') return;
          if (code === 'no-speech') setMessage({ kind: 'error', text: text.no_speech });
          else if (code === 'not-allowed') setMessage({ kind: 'error', text: text.denied });
          else if (code === 'audio-capture') setMessage({ kind: 'error', text: text.no_mic });
          else setMessage({ kind: 'error', text: text.unavailable });
        },
        onEnd: () => {
          if (!alive.current) return;
          session.current = null;
          setPhase('idle');
        },
      });
    } catch {
      session.current = null;
      setPhase('dictating');
      setMessage(null);
    }
  };

  const press = () => {
    if (phase === 'listening') {
      stop();
      return;
    }
    if (phase === 'dictating') {
      setPhase('idle');
      return;
    }
    if (supported) start();
    else {
      setMessage(null);
      setTyped('');
      setPhase('dictating');
    }
  };

  const openDictation = () => {
    session.current?.abort();
    session.current = null;
    setTyped('');
    setMessage(null);
    setPhase('dictating');
  };

  const preview = typed.trim() === '' ? null : parseSpokenNumber(typed, mode);
  const insert = () => {
    if (preview === null) return;
    accept(typed, preview);
    setPhase('idle');
  };

  const changeLang = (next: SpeechLang) => {
    setLang(next);
    saveSpeechLang(next);
  };

  const active = phase === 'listening';
  return (
    <div className={`space-y-1.5 ${className}`.trim()}>
      <div className="flex items-stretch gap-2">
        {children}
        <button
          type="button"
          aria-label={`voice-${name}`}
          aria-pressed={active}
          title={text.mic}
          disabled={disabled}
          onClick={press}
          className={`${mic} ${active ? 'bg-red-600 border-red-600 text-white animate-pulse' : 'pe-surface border-slate-200 text-slate-700'}`}
        >
          <span aria-hidden="true">{active ? '⏹' : '🎤'}</span>
          <span className="sr-only">{active ? text.stop : text.mic}</span>
        </button>
      </div>

      {phase === 'dictating' && (
        <div aria-label={`voice-panel-${name}`} className="pe-card rounded-xl border border-slate-200 p-3 space-y-2">
          <p className="text-sm font-semibold text-slate-900 break-words">{text.dictate_title}</p>
          <p className="text-xs text-slate-600 break-words">{text.dictate_hint}</p>
          <p className="text-xs text-slate-500 break-words">{mode === 'length' ? text.examples_length : text.examples_plain}</p>
          <label htmlFor={typedId} className="sr-only">{text.dictate_title}</label>
          <input
            id={typedId}
            aria-label={`voice-text-${name}`}
            autoFocus
            autoComplete="off"
            value={typed}
            placeholder={text.dictate_placeholder}
            onChange={(event) => setTyped(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                insert();
              }
            }}
            className="w-full min-h-11 border border-slate-200 rounded-xl px-3 py-2 text-base text-slate-900 pe-surface"
          />
          <p aria-label={`voice-preview-${name}`} className={`text-sm break-words ${preview === null ? 'text-slate-500' : 'font-semibold text-slate-900'}`}>
            {preview === null ? text.dictate_none : text.dictate_preview.replace('{value}', shown(preview))}
          </p>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              aria-label={`voice-insert-${name}`}
              disabled={preview === null}
              onClick={insert}
              className="w-full min-h-11 px-4 py-2 text-sm bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-50"
            >
              <Ico>✅</Ico>{text.insert}
            </button>
            <button
              type="button"
              aria-label={`voice-close-${name}`}
              onClick={() => setPhase('idle')}
              className="w-full min-h-11 px-4 py-2 text-sm rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium"
            >
              <Ico>✖️</Ico>{t.common.close}
            </button>
          </div>
        </div>
      )}

      {phase !== 'dictating' && message && (
        <div aria-label={`voice-status-${name}`} role={message.kind === 'error' ? 'alert' : 'status'} className="space-y-1.5">
          <p className={`text-xs break-words ${message.kind === 'error' ? 'text-red-600' : message.kind === 'ok' ? 'text-emerald-800' : 'text-slate-600'}`}>{message.text}</p>
          {phase === 'idle' && message.kind === 'error' && (
            <button
              type="button"
              aria-label={`voice-keyboard-${name}`}
              onClick={openDictation}
              className="w-full min-h-11 px-3 py-2 text-sm rounded-xl border border-slate-200 pe-surface text-slate-700 font-medium"
            >
              <Ico>⌨️</Ico>{text.keyboard}
            </button>
          )}
        </div>
      )}

      {supported && phase !== 'dictating' && (phase === 'listening' || message) && (
        <div className="flex items-center gap-2">
          <label htmlFor={langId} className="text-xs text-slate-600 shrink-0">{text.language}</label>
          <select
            id={langId}
            aria-label={`voice-lang-${name}`}
            value={lang}
            disabled={phase === 'listening'}
            onChange={(event) => changeLang(event.target.value as SpeechLang)}
            className="min-h-11 flex-1 min-w-0 border border-slate-200 rounded-xl px-2 text-sm text-slate-900 pe-surface"
          >
            {SPEECH_LANGS.map((code) => (
              <option key={code} value={code}>{LOCALE_NAMES[code]}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
