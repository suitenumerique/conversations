import { useCallback, useRef, useState } from 'react';

import { fetchAPI } from '@/api';
import { on } from 'events';

export type RecordingState = 'idle' | 'recording' | 'transcribing';

interface UseAudioRecordingOptions {
  onTranscription: (text: string) => void;
  onTranscriptionError?: () => void;
}

export const useAudioRecording = ({
  onTranscription,
  onTranscriptionError,
}: UseAudioRecordingOptions) => {
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [volume, setVolume] = useState(0);

  const onTranscriptionRef = useRef(onTranscription);
  onTranscriptionRef.current = onTranscription;

  const onTranscriptionErrorRef = useRef(onTranscriptionError);
  onTranscriptionErrorRef.current = onTranscriptionError;

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number>(0);
  const audioCtxRef = useRef<AudioContext | null>(null);

  const stopVisualization = useCallback(() => {
    cancelAnimationFrame(animFrameRef.current);
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    setVolume(0);
  }, []);

  const startVisualization = useCallback((stream: MediaStream) => {
    const audioCtx = new AudioContext();
    audioCtxRef.current = audioCtx;
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    const dataArray = new Uint8Array(analyser.fftSize);

    const tick = () => {
      analyser.getByteTimeDomainData(dataArray);
      // RMS amplitude: 0 = silence, 1 = full scale
      const rms =
        Math.sqrt(
          dataArray.reduce((sum, v) => sum + (v - 128) ** 2, 0) /
          dataArray.length,
        ) / 128;
      setVolume(rms);
      animFrameRef.current = requestAnimationFrame(tick);
    };
    tick();
  }, []);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    stopVisualization();
  }, [stopVisualization]);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      startVisualization(stream);
      setRecordingState('recording');
      const mediaRecorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      mediaRecorder.start();
      mediaRecorderRef.current = mediaRecorder;
    } catch {
      setRecordingState('idle');
      onTranscriptionErrorRef.current?.();
    }
  }, [startVisualization]);

  const confirmRecording = useCallback(async () => {
    if (mediaRecorderRef.current) {
      const recorder = mediaRecorderRef.current;
      mediaRecorderRef.current = null;

      recorder.onstop = async () => {
        stopStream();
        setRecordingState('transcribing');

        const mimeType = recorder.mimeType || 'audio/webm';
        const ext = mimeType.includes('mp4') ? 'mp4' : 'webm';
        const blob = new Blob(audioChunksRef.current, { type: mimeType });
        const form = new FormData();
        form.append('audio', blob, `recording.${ext}`);

        try {
          const res = await fetchAPI('transcribe/', {
            method: 'POST',
            body: form,
            withoutContentType: true,
          });
          const data = await res.json();
          if (data.error) onTranscriptionErrorRef.current?.();
          if (data.text) onTranscriptionRef.current(data.text);
        } catch {
          onTranscriptionErrorRef.current?.();
        } finally {
          setRecordingState('idle');
        }
      };

      recorder.stop();
    }
  }, [stopStream]);

  const cancelRecording = useCallback(() => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
    stopStream();
    setRecordingState('idle');
  }, [stopStream]);

  return {
    recordingState,
    volume,
    startRecording,
    confirmRecording,
    cancelRecording,
  };
};
