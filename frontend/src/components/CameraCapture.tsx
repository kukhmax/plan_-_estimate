import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { usePhotoBackRegistration } from '../hooks/PhotoBackContext';
import { useI18n } from '../hooks/useI18n';
import {
  CameraFailure,
  CameraSession,
  classifyCameraError,
  closeCamera,
  openCamera,
  setTorch,
  takeStill,
} from '../utils/inAppCamera';
import { MAX_FILES_PER_SELECTION } from '../utils/photoUploadQueue';
import { hapticNotify } from '../utils/telegramHaptics';
import { CameraIcon, CloseIcon } from './PhotoIcons';

// The viewfinder (Stage 14E.10): a full-screen camera with a series mode — shot after shot without leaving the screen,
// then "Gotowe" hands all the files over to the upload queue at once. Nothing is uploaded from here.
// Telegram's BackButton closes it through the photo back registry; with unsent shots the close asks first.

interface CameraCaptureProps {
  /** The shots, in order; called once, when the user presses "Gotowe". */
  onDone: (files: File[]) => void;
  /** Closed without handing anything over (nothing was taken, or the user discarded the shots). */
  onCancel: () => void;
  /** The camera cannot be used: the parent opens the phone's own picker (this runs inside the user's tap). */
  onUseNativePicker: () => void;
  /** Called with the failure when the camera is refused, so the parent can stop offering it this session. */
  onCameraFailed?: (failure: CameraFailure) => void;
}

type Phase = 'starting' | 'live' | 'failed';

export function CameraCapture({ onDone, onCancel, onUseNativePicker, onCameraFailed }: CameraCaptureProps) {
  const { t } = useI18n();
  const videoRef = useRef<HTMLVideoElement>(null);
  const sessionRef = useRef<CameraSession | null>(null);
  const shotCounter = useRef(0);
  const [phase, setPhase] = useState<Phase>('starting');
  const [failure, setFailure] = useState<CameraFailure>('unknown');
  const [shots, setShots] = useState<File[]>([]);
  const [lastUrl, setLastUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [torch, setTorchState] = useState(false);
  const [hasTorch, setHasTorch] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const aliveRef = useRef(true);
  const failedRef = useRef(onCameraFailed);
  useEffect(() => {
    failedRef.current = onCameraFailed;
  }, [onCameraFailed]);

  const releaseCamera = useCallback(() => {
    closeCamera(sessionRef.current);
    sessionRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  const startCamera = useCallback(async () => {
    releaseCamera();
    setPhase('starting');
    try {
      const session = await openCamera();
      if (!aliveRef.current) return closeCamera(session);
      sessionRef.current = session;
      setHasTorch(session.hasTorch);
      setTorchState(false);
      session.track.addEventListener('ended', () => {
        if (sessionRef.current !== session || !aliveRef.current) return;
        sessionRef.current = null;
        setNote(t.photos.camera.interrupted);
        void startCamera();
      });
      if (videoRef.current) {
        videoRef.current.srcObject = session.stream;
        await videoRef.current.play().catch(() => undefined); // autoplay is also set; a refused play() is retried by the browser
      }
      setPhase('live');
    } catch (error) {
      if (!aliveRef.current) return;
      const reason = classifyCameraError(error);
      setFailure(reason);
      setPhase('failed');
      failedRef.current?.(reason);
    }
  }, [releaseCamera, t]);

  useEffect(() => {
    aliveRef.current = true;
    void startCamera();
    return () => {
      aliveRef.current = false;
      releaseCamera();
    };
    // starts once per mount; later restarts go through the button or the visibility handler
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The host may stop the camera when the app goes to the background: release it, and start it again on return.
  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) {
        releaseCamera();
      } else if (aliveRef.current && !sessionRef.current && phase !== 'failed') {
        void startCamera();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [phase, releaseCamera, startCamera]);

  useEffect(() => {
    return () => {
      if (lastUrl) URL.revokeObjectURL(lastUrl);
    };
  }, [lastUrl]);

  const requestClose = useCallback(() => {
    if (confirmDiscard) return setConfirmDiscard(false);
    if (shots.length === 0) {
      releaseCamera();
      return onCancel();
    }
    setConfirmDiscard(true);
  }, [confirmDiscard, shots.length, onCancel, releaseCamera]);
  usePhotoBackRegistration(true, requestClose);

  const shoot = async () => {
    const session = sessionRef.current;
    if (!session || busy || shots.length >= MAX_FILES_PER_SELECTION) return;
    setBusy(true);
    setNote(t.photos.camera.saving);
    try {
      shotCounter.current += 1;
      const file = await takeStill(session, shotCounter.current);
      setShots((current) => [...current, file]);
      setLastUrl(URL.createObjectURL(file));
      setNote(null);
      setFlash(true);
      window.setTimeout(() => setFlash(false), 140);
      hapticNotify('success');
    } catch {
      shotCounter.current -= 1;
      setNote(t.photos.camera.capture_failed);
      hapticNotify('error');
    } finally {
      setBusy(false);
    }
  };

  const toggleTorch = async () => {
    const session = sessionRef.current;
    if (!session) return;
    try {
      await setTorch(session, !torch);
      setTorchState(!torch);
    } catch {
      setNote(t.photos.camera.torch_failed);
    }
  };

  const finish = () => {
    releaseCamera();
    onDone(shots);
  };

  const full = shots.length >= MAX_FILES_PER_SELECTION;
  const failureText: Record<CameraFailure, string> = {
    denied: t.photos.camera.denied,
    busy: t.photos.camera.busy,
    unavailable: t.photos.camera.missing,
    unsupported: t.photos.camera.generic,
    unknown: t.photos.camera.generic,
  };
  const round = 'flex shrink-0 items-center justify-center rounded-full bg-white/15 text-white';

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.photos.camera.title}
      className="fixed inset-0 z-[70] flex flex-col bg-black text-white"
      style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 px-3 py-2">
        <button type="button" aria-label={t.photos.camera.close} onClick={requestClose} className={`${round} min-h-11 min-w-11`}>
          <CloseIcon />
        </button>
        <p role="status" className="min-w-0 flex-1 break-words text-center text-sm font-semibold">
          {t.photos.camera.counter.replace('{count}', String(shots.length)).replace('{max}', String(MAX_FILES_PER_SELECTION))}
        </p>
        {hasTorch ? (
          <button
            type="button"
            aria-label={torch ? t.photos.camera.torch_off : t.photos.camera.torch_on}
            aria-pressed={torch}
            onClick={toggleTorch}
            className={`${round} min-h-11 min-w-11 ${torch ? 'bg-amber-400 text-black' : ''}`}
          >
            <span aria-hidden="true" className="text-lg leading-none">
              ⚡
            </span>
          </button>
        ) : (
          <span className="min-w-11" aria-hidden="true" />
        )}
      </div>

      <div className="relative min-h-0 flex-1">
        <video ref={videoRef} playsInline muted autoPlay className="h-full w-full bg-black object-contain" aria-label="camera-preview" />
        {flash && <div data-testid="camera-flash" className="pointer-events-none absolute inset-0 bg-white/70" />}
        {phase === 'starting' && (
          <p className="absolute inset-0 flex items-center justify-center px-6 text-center text-sm">{t.photos.camera.starting}</p>
        )}
        {phase === 'failed' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
            <h2 className="break-words text-base font-semibold">{t.photos.camera.unavailable_title}</h2>
            <p className="break-words text-sm text-white/80">{failureText[failure]}</p>
            {failure !== 'denied' && failure !== 'unsupported' && (
              <button
                type="button"
                onClick={() => void startCamera()}
                className="min-h-11 w-full max-w-xs rounded-xl border border-white/40 px-3 py-2 text-sm font-semibold"
              >
                {t.photos.camera.restart}
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                releaseCamera();
                onUseNativePicker();
              }}
              className="min-h-11 w-full max-w-xs rounded-xl bg-white px-3 py-2 text-sm font-semibold text-black"
            >
              {t.photos.camera.use_phone_picker}
            </button>
          </div>
        )}
      </div>

      {note && (
        <p role="alert" className="shrink-0 break-words px-4 py-1 text-center text-xs text-amber-300">
          {note}
        </p>
      )}
      {full && <p className="shrink-0 break-words px-4 py-1 text-center text-xs text-amber-300">{t.photos.camera.limit_reached.replace('{max}', String(MAX_FILES_PER_SELECTION))}</p>}

      <div className="flex shrink-0 items-center justify-between gap-3 px-3 py-3">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white/10">
          {lastUrl && <img src={lastUrl} alt={t.photos.camera.last_shot} className="h-full w-full object-cover" />}
        </div>
        <button
          type="button"
          aria-label={t.photos.camera.shutter}
          disabled={phase !== 'live' || busy || full}
          onClick={shoot}
          className="flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full border-4 border-white bg-white/20 text-white disabled:opacity-40"
        >
          <CameraIcon size={28} />
        </button>
        <button
          type="button"
          disabled={shots.length === 0}
          onClick={finish}
          className="min-h-11 min-w-0 flex-1 break-words rounded-xl bg-[var(--tg-theme-button-color,#2481cc)] px-3 py-2 text-sm font-semibold text-[var(--tg-theme-button-text-color,#fff)] disabled:opacity-40"
        >
          {t.photos.camera.done.replace('{count}', String(shots.length))}
        </button>
      </div>

      {confirmDiscard && (
        <div role="alertdialog" aria-label={t.photos.camera.discard_title} className="absolute inset-0 z-10 flex items-center justify-center bg-black/80 p-6">
          <div className="w-full max-w-xs space-y-3 rounded-2xl bg-neutral-900 p-4 text-center">
            <h2 className="break-words text-base font-semibold">{t.photos.camera.discard_title}</h2>
            <p className="break-words text-sm text-white/80">{t.photos.camera.discard_text.replace('{count}', String(shots.length))}</p>
            <button type="button" onClick={() => setConfirmDiscard(false)} className="min-h-11 w-full rounded-xl bg-white px-3 py-2 text-sm font-semibold text-black">
              {t.photos.camera.discard_keep}
            </button>
            <button
              type="button"
              onClick={() => {
                releaseCamera();
                onCancel();
              }}
              className="min-h-11 w-full rounded-xl border border-red-400 px-3 py-2 text-sm font-semibold text-red-300"
            >
              {t.photos.camera.discard_confirm}
            </button>
          </div>
        </div>
      )}
    </div>,
    document.body,
  );
}
