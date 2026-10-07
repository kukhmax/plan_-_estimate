import { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../hooks/useI18n';
import {
  PROBE_PRESETS,
  ProbePreset,
  StillResult,
  buildConstraints,
  captureFromVideo,
  captureWithImageCapture,
  describeDevices,
  describeEnvironment,
  describeError,
  describePermission,
  describeTrack,
} from '../utils/cameraProbe';

// Stage 14E.9 spike: a throwaway diagnostic screen (opened from the account window) that answers one question — can this
// page use the phone camera inside Telegram, and what does it get? It stores and sends nothing; the whole result is the
// text report below, which the owner reads out or screenshots. The report lines are technical data, not UI copy.

interface CameraSpikeProps {
  onClose: () => void;
}

interface StillView {
  id: number;
  method: StillResult['method'];
  url: string;
}

export function CameraSpike({ onClose }: CameraSpikeProps) {
  const { t } = useI18n();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const stillId = useRef(0);
  const [lines, setLines] = useState<string[]>(() => ['== environment ==', ...describeEnvironment(window)]);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stills, setStills] = useState<StillView[]>([]);
  const [copyNote, setCopyNote] = useState<string | null>(null);

  const log = useCallback((...added: string[]) => setLines((current) => [...current, ...added]), []);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setRunning(false);
  }, []);

  // The camera must never stay on after the screen is gone; object URLs of the test shots are released with it.
  useEffect(() => stopStream, [stopStream]);
  useEffect(
    () => () => {
      stills.forEach((still) => URL.revokeObjectURL(still.url));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const start = async (preset: ProbePreset) => {
    stopStream();
    setBusy(true);
    log(`== start ${preset.id} (${preset.width}x${preset.height}) ==`);
    log(await describePermission(window));
    const started = performance.now();
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('navigator.mediaDevices.getUserMedia is not available');
      const stream = await navigator.mediaDevices.getUserMedia(buildConstraints(preset));
      streamRef.current = stream;
      const track = stream.getVideoTracks()[0];
      log(`getUserMedia ok in ${Math.round(performance.now() - started)} ms`);
      if (track) log(...describeTrack(track));
      log(await describeDevices(navigator.mediaDevices));
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        try {
          await videoRef.current.play();
          log(`preview playing ${videoRef.current.videoWidth}x${videoRef.current.videoHeight}`);
        } catch (error) {
          log(`preview play failed: ${describeError(error)}`);
        }
      }
      track?.addEventListener('ended', () => log('track ended (the host stopped the camera)'));
      setRunning(true);
    } catch (error) {
      log(`getUserMedia failed in ${Math.round(performance.now() - started)} ms: ${describeError(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const keepStill = (result: StillResult) => {
    log(result.line);
    if (result.ok && result.blob) {
      stillId.current += 1;
      setStills((current) => [...current, { id: stillId.current, method: result.method, url: URL.createObjectURL(result.blob as Blob) }]);
    }
  };

  const takePhoto = async () => {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track) return log('takePhoto: the camera is not running');
    setBusy(true);
    try {
      keepStill(await captureWithImageCapture(track));
    } finally {
      setBusy(false);
    }
  };

  const takeCanvas = async () => {
    if (!videoRef.current || !streamRef.current) return log('canvas: the camera is not running');
    setBusy(true);
    try {
      keepStill(await captureFromVideo(videoRef.current));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard is not available');
      await navigator.clipboard.writeText(lines.join('\n'));
      setCopyNote(t.cameraSpike.copied);
    } catch (error) {
      log(`copy failed: ${describeError(error)}`);
      setCopyNote(t.cameraSpike.copy_manual);
    }
  };

  const button =
    'flex min-h-11 w-full min-w-0 items-center justify-center rounded-xl px-3 py-2 text-sm font-semibold transition disabled:opacity-50';
  const primary = `${button} bg-[var(--tg-theme-button-color)] text-[var(--tg-theme-button-text-color)]`;
  const secondary = `${button} border border-[var(--tg-control-border-color)] bg-[var(--tg-theme-secondary-bg-color)] text-[var(--tg-theme-text-color)]`;
  const startLabels: Record<ProbePreset['id'], string> = {
    max: t.cameraSpike.start_max,
    fhd: t.cameraSpike.start_fhd,
    hd: t.cameraSpike.start_hd,
  };

  return (
    <div
      className="fixed inset-0 z-[60] overflow-y-auto"
      style={{ backgroundColor: 'var(--tg-theme-bg-color)', color: 'var(--tg-theme-text-color)' }}
      role="dialog"
      aria-modal="true"
      aria-label={t.cameraSpike.title}
    >
      <div className="mx-auto w-full max-w-md space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 break-words text-lg font-bold">{t.cameraSpike.title}</h2>
          <button
            type="button"
            aria-label={t.cameraSpike.close}
            onClick={() => {
              stopStream();
              onClose();
            }}
            className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-xl border text-xl font-semibold"
            style={{ borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))' }}
          >
            ×
          </button>
        </div>
        <p className="break-words text-sm" style={{ color: 'var(--tg-theme-hint-color)' }}>
          {t.cameraSpike.intro}
        </p>

        <div className="grid grid-cols-1 gap-2">
          {PROBE_PRESETS.map((preset) => (
            <button key={preset.id} type="button" disabled={busy} onClick={() => start(preset)} className={preset.id === 'max' ? primary : secondary}>
              <span className="min-w-0 break-words">{startLabels[preset.id]}</span>
            </button>
          ))}
        </div>

        <video
          ref={videoRef}
          playsInline
          muted
          autoPlay
          className="max-h-[50vh] w-full rounded-xl bg-black object-contain"
          aria-label="camera-preview"
        />

        <div className="grid grid-cols-1 gap-2 min-[360px]:grid-cols-2">
          <button type="button" disabled={busy || !running} onClick={takePhoto} className={primary}>
            <span className="min-w-0 break-words">{t.cameraSpike.take_photo}</span>
          </button>
          <button type="button" disabled={busy || !running} onClick={takeCanvas} className={primary}>
            <span className="min-w-0 break-words">{t.cameraSpike.take_canvas}</span>
          </button>
        </div>
        <button type="button" disabled={!running} onClick={stopStream} className={secondary}>
          <span className="min-w-0 break-words">{t.cameraSpike.stop}</span>
        </button>

        {stills.length > 0 && (
          <section aria-label={t.cameraSpike.stills} className="space-y-2">
            <h3 className="text-sm font-semibold">{t.cameraSpike.stills}</h3>
            <div className="grid grid-cols-2 gap-2">
              {stills.map((still) => (
                <figure key={still.id} className="min-w-0">
                  <img src={still.url} alt={still.method} className="aspect-[4/3] w-full rounded-lg bg-black object-cover" />
                  <figcaption className="break-words text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
                    #{still.id} {still.method}
                  </figcaption>
                </figure>
              ))}
            </div>
          </section>
        )}

        <section aria-label={t.cameraSpike.report} className="space-y-2">
          <h3 className="text-sm font-semibold">{t.cameraSpike.report}</h3>
          <pre
            className="max-h-[40vh] overflow-y-auto whitespace-pre-wrap break-words rounded-xl border p-3 text-xs"
            style={{ borderColor: 'var(--tg-control-border-color, var(--tg-theme-hint-color))' }}
            data-testid="camera-report"
          >
            {lines.join('\n')}
          </pre>
          <button type="button" onClick={copy} className={secondary}>
            <span className="min-w-0 break-words">{t.cameraSpike.copy}</span>
          </button>
          {copyNote && (
            <p role="status" className="break-words text-xs" style={{ color: 'var(--tg-theme-hint-color)' }}>
              {copyNote}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
