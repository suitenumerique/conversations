import { Button } from '@gouvfr-lasuite/cunningham-react';
import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon } from '@/components';

import { RecordingState } from '../hooks/useAudioRecording';

interface AudioRecordButtonProps {
  disabled?: boolean;
  recordingState: RecordingState;
  onStartRecording: () => void;
  onConfirm: () => void;
  onCancel: () => void;
  volume: number;
}

const BAR_COUNT = 40;
const SAMPLE_INTERVAL_MS = 80;

const SPINNER_CSS = `
  width: 20px;
  height: 20px;
  border: 2px solid var(--c--contextuals--border--surface--primary);
  border-top-color: var(--c--contextuals--content--semantic--brand--primary);
  border-radius: 50%;
  animation: audio-spin 0.7s linear infinite;

  @keyframes audio-spin {
    to { transform: rotate(360deg); }
  }
`;

const RECORDING_BAR_CSS = `
  padding: 0 1rem;
  min-height: 14px;
`;

const WAVEFORM_WRAPPER_STYLE: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  gap: '2px',
  overflow: 'hidden',
  height: '36px',
  padding: '0 0.5rem',
};

export const AudioRecordButton = ({
  recordingState,
  onStartRecording,
  onConfirm,
  onCancel,
  volume,
  disabled,
}: AudioRecordButtonProps) => {
  const { t } = useTranslation();

  if (recordingState === 'idle') {
    return (
      <Button
        size="small"
        type="button"
        color="neutral"
        variant="tertiary"
        className="c__button--neutral c__button--mic"
        onClick={onStartRecording}
        aria-label={t('Record audio')}
        icon={<Icon iconName="mic" />}
        disabled={disabled}
      />
    );
  }

  if (recordingState === 'transcribing') {
    return (
      <Box
        $direction="row"
        $align="center"
        $justify="center"
        $flex="1"
        $css={RECORDING_BAR_CSS}
      >
        <Box $css={SPINNER_CSS} />
      </Box>
    );
  }

  return (
    <RecordingButton recordingState={recordingState} onCancel={onCancel} onConfirm={onConfirm} volume={volume} />
  );
}

interface RecordingButtonProps {
  recordingState: RecordingState;
  onConfirm: () => void;
  onCancel: () => void;
  volume: number;
}

const RecordingButton = ({
  recordingState,
  onCancel,
  onConfirm,
  volume,
}: RecordingButtonProps) => {
  const { t } = useTranslation();

  const [history, setHistory] = useState<number[]>(
    Array(BAR_COUNT).fill(0),
  );

  const volumeRef = useRef<number>(volume);
  volumeRef.current = volume;

  useEffect(() => {
    if (recordingState !== 'recording') return;
    if (volumeRef.current === undefined) return;

    const interval = setInterval(() => {
      setHistory((prev) => [...prev.slice(1), volumeRef.current]);
    }, SAMPLE_INTERVAL_MS);
    return () => {
      clearInterval(interval);
      setHistory(Array(BAR_COUNT).fill(0));
    };
  }, [recordingState]);

  return (
    <Box $direction="row" $align="center" $flex="1" $css={RECORDING_BAR_CSS}>
      <div style={WAVEFORM_WRAPPER_STYLE}>
        {history.map((level, i) => {
          // Amplify RMS values
          const height = Math.max(3, Math.min(32, level * 400));
          const opacity = 0.3 + (i / BAR_COUNT) * 0.7;
          return (
            <div
              key={i}
              style={{
                flex: 1,
                height: `${height}px`,
                background: 'var(--c--contextuals--border--semantic--brand--primary)',
                opacity,
                borderRadius: '2px',
              }}
            />
          );
        })}
      </div>

      <Box $direction="row" $gap="sm">
        <Button
          size="small"
          type="button"
          color="neutral"
          variant="tertiary"
          onClick={onCancel}
          aria-label={t('Cancel recording')}
          icon={<Icon iconName="close" />}
        />
        <Button
          size="small"
          type="button"
          color="neutral"
          variant="tertiary"
          onClick={onConfirm}
          aria-label={t('Confirm recording')}
          icon={<Icon iconName="check" />}
        />
      </Box>
    </Box>
  );
};
