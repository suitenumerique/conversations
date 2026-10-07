import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchAPI } from '@/api';

export type VoicePromptState = 'idle' | 'recording' | 'transcribing';

export type VoicePromptError =
  'permission' | 'empty' | 'too-large' | 'throttled' | 'failed';

interface UseVoicePromptOptions {
  maxDurationSeconds: number;
  onTranscript: (text: string) => void;
  onError: (error: VoicePromptError) => void;
}

// Plenty for speech, and keeps 5 minutes around 1.2 MB.
const AUDIO_BITS_PER_SECOND = 32000;
const TIMER_TICK_MS = 250;
const ANALYSER_FFT_SIZE = 1024;

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
  const cancelledRef = useRef(false);
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
    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = ANALYSER_FFT_SIZE;
    audioContext.createMediaStreamSource(stream).connect(analyser);
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
    async (recording: Blob) => {
      setState('transcribing');
      try {
        const body = new FormData();
        body.append('audio', recording, 'voice-prompt');
        const response = await fetchAPI('transcriptions/', {
          method: 'POST',
          body,
          withoutContentType: true,
        });
        if (!response.ok) {
          onError(errorFromStatus(response.status));
          return;
        }
        const { text } = (await response.json()) as { text: string };
        if (text.trim()) {
          onTranscript(text.trim());
        } else {
          onError('empty');
        }
      } catch {
        onError('failed');
      } finally {
        setState('idle');
      }
    },
    [onError, onTranscript],
  );

  const start = useCallback(async () => {
    if (startingRef.current || recorderRef.current) {
      return;
    }
    startingRef.current = true;
    cancelledRef.current = false;
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      onError('permission');
      return;
    } finally {
      startingRef.current = false;
    }
    // The input went away while the permission prompt was open.
    if (cancelledRef.current) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }

    const recorder = new MediaRecorder(stream, {
      audioBitsPerSecond: AUDIO_BITS_PER_SECOND,
    });
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };
    recorder.onstop = () => {
      stopMetering();
      stream.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
      if (cancelledRef.current) {
        setState('idle');
        return;
      }
      void transcribe(new Blob(chunksRef.current, { type: recorder.mimeType }));
    };

    recorder.start();
    recorderRef.current = recorder;
    startMetering(stream);
    startedAtRef.current = Date.now();
    setElapsedSeconds(0);
    setState('recording');
  }, [onError, transcribe, startMetering, stopMetering]);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    stopRecorder();
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

  // Release the microphone if the input goes away mid-recording.
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
