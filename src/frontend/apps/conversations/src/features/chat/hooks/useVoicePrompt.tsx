import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchAPI } from '@/api';

export type VoicePromptState = 'idle' | 'recording' | 'transcribing';

export type VoicePromptError =
  'permission' | 'microphone' | 'empty' | 'too-large' | 'throttled' | 'failed';

interface UseVoicePromptOptions {
  maxDurationSeconds: number;
  onTranscript: (text: string) => void;
  onError: (error: VoicePromptError) => void;
}

// Plenty for speech, and keeps 5 minutes around 1.2 MB.
const AUDIO_BITS_PER_SECOND = 32000;
const TIMER_TICK_MS = 250;
const ANALYSER_FFT_SIZE = 1024;
// Formats the backend accepts, best first: webm (Chrome, Firefox, Edge,
// Safari 18.4+), then mp4 (older Safari). Each browser's default differs.
const RECORDING_MIME_TYPES = ['audio/webm', 'audio/mp4'];

const pickMimeType = () =>
  RECORDING_MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));

const errorFromStatus = (status: number): VoicePromptError => {
  if (status === 413) {
    return 'too-large';
  }
  if (status === 429) {
    return 'throttled';
  }
  return 'failed';
};

/**
 * Record a Voice prompt with the browser's MediaRecorder and turn it into a
 * Transcript. The recording is sent as-is (webm or mp4 depending on the
 * browser) and never kept once transcribed.
 *
 * While recording, `getVolume` returns the microphone's RMS level (0 to 1).
 * It is read from a ref rather than exposed as state so that metering on
 * every animation frame does not re-render the whole chat input.
 */
export const useVoicePrompt = ({
  maxDurationSeconds,
  onTranscript,
  onError,
}: UseVoicePromptOptions) => {
  const [state, setState] = useState<VoicePromptState>('idle');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  // Bumped by every start and cancel: a recording or transcription that ends
  // after either belongs to a dictation the user has left.
  const sessionRef = useRef(0);
  // Set from the click until the recorder runs: the permission prompt can sit
  // open while the user clicks the mic again.
  const startingRef = useRef(false);
  const startedAtRef = useRef(0);
  const volumeRef = useRef(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationFrameRef = useRef(0);

  const startMetering = useCallback((stream: MediaStream) => {
    // Not available in jsdom and some older browsers: record without a level.
    if (typeof AudioContext === 'undefined') {
      return;
    }
    let analyser: AnalyserNode;
    try {
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      analyser = audioContext.createAnalyser();
      analyser.fftSize = ANALYSER_FFT_SIZE;
      audioContext.createMediaStreamSource(stream).connect(analyser);
    } catch {
      // The level is cosmetic: keep recording without it.
      void audioContextRef.current?.close();
      audioContextRef.current = null;
      return;
    }
    const samples = new Uint8Array(analyser.fftSize);

    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      // Samples are centered on 128; RMS 0 is silence, 1 is full scale.
      const sumOfSquares = samples.reduce(
        (sum, sample) => sum + (sample - 128) ** 2,
        0,
      );
      volumeRef.current = Math.sqrt(sumOfSquares / samples.length) / 128;
      animationFrameRef.current = requestAnimationFrame(tick);
    };
    tick();
  }, []);

  const stopMetering = useCallback(() => {
    cancelAnimationFrame(animationFrameRef.current);
    void audioContextRef.current?.close();
    audioContextRef.current = null;
    volumeRef.current = 0;
  }, []);

  const getVolume = useCallback(() => volumeRef.current, []);

  // MediaRecorder.stop() throws once the recorder is inactive, and both the
  // user and the duration cap can ask for a stop.
  const stopRecorder = useCallback(() => {
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop();
    }
  }, []);

  const transcribe = useCallback(
    async (recording: Blob, session: number) => {
      const isStale = () => session !== sessionRef.current;
      setState('transcribing');
      try {
        const body = new FormData();
        body.append('audio', recording, 'voice-prompt');
        const response = await fetchAPI('voice-prompt/transcriptions/', {
          method: 'POST',
          body,
          withoutContentType: true,
        });
        const text = response.ok
          ? ((await response.json()) as { text: string }).text.trim()
          : '';
        if (isStale()) {
          return;
        }
        if (!response.ok) {
          onError(errorFromStatus(response.status));
        } else if (text) {
          onTranscript(text);
        } else {
          onError('empty');
        }
      } catch {
        if (!isStale()) {
          onError('failed');
        }
      } finally {
        if (!isStale()) {
          setState('idle');
        }
      }
    },
    [onError, onTranscript],
  );

  const start = useCallback(async () => {
    if (startingRef.current || recorderRef.current) {
      return;
    }
    startingRef.current = true;
    const session = ++sessionRef.current;
    let stream: MediaStream;
    try {
      // Throws a TypeError when mediaDevices is missing (page not on HTTPS).
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      onError(
        error instanceof DOMException && error.name === 'NotAllowedError'
          ? 'permission'
          : 'microphone',
      );
      return;
    } finally {
      startingRef.current = false;
    }
    const releaseMicrophone = () =>
      stream.getTracks().forEach((track) => track.stop());
    // The dictation was cancelled while the permission prompt was open.
    if (session !== sessionRef.current) {
      releaseMicrophone();
      return;
    }

    let recorder: MediaRecorder;
    try {
      const mimeType = pickMimeType();
      recorder = new MediaRecorder(stream, {
        audioBitsPerSecond: AUDIO_BITS_PER_SECOND,
        ...(mimeType && { mimeType }),
      });
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        stopMetering();
        releaseMicrophone();
        recorderRef.current = null;
        if (session !== sessionRef.current) {
          return;
        }
        void transcribe(
          new Blob(chunksRef.current, { type: recorder.mimeType }),
          session,
        );
      };
      recorder.start();
    } catch {
      // MediaRecorder missing or refusing this stream.
      releaseMicrophone();
      onError('microphone');
      return;
    }
    recorderRef.current = recorder;
    startMetering(stream);
    startedAtRef.current = Date.now();
    setElapsedSeconds(0);
    setState('recording');
  }, [onError, transcribe, startMetering, stopMetering]);

  const cancel = useCallback(() => {
    sessionRef.current += 1;
    stopRecorder();
    setState('idle');
  }, [stopRecorder]);

  // Elapsed-time display and auto-stop at the cap.
  useEffect(() => {
    if (state !== 'recording') {
      return;
    }
    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAtRef.current) / 1000);
      setElapsedSeconds(Math.min(elapsed, maxDurationSeconds));
      if (elapsed >= maxDurationSeconds) {
        stopRecorder();
      }
    }, TIMER_TICK_MS);
    return () => clearInterval(interval);
  }, [state, maxDurationSeconds, stopRecorder]);

  // Enter confirms the recording, Escape discards it. Enter on a focused
  // button is left to that button, and Shift+Enter still types a new line.
  useEffect(() => {
    if (state !== 'recording') {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        cancel();
      } else if (
        event.key === 'Enter' &&
        !event.shiftKey &&
        !(event.target instanceof HTMLButtonElement)
      ) {
        event.preventDefault();
        stopRecorder();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [state, cancel, stopRecorder]);

  // Release the microphone and drop the transcription if the input goes away.
  useEffect(() => cancel, [cancel]);

  return {
    state,
    elapsedSeconds,
    getVolume,
    start,
    stop: stopRecorder,
    cancel,
  };
};
