import { Button } from '@gouvfr-lasuite/cunningham-react';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';

const BAR_COUNT = 40;
const SAMPLE_INTERVAL_MS = 80;

const SPINNER_CSS = `
  width: 20px;
  height: 20px;
  border: 2px solid var(--c--contextuals--border--surface--primary);
  border-top-color: var(--c--contextuals--content--semantic--brand--primary);
  border-radius: 50%;
  animation: voice-prompt-spin 0.7s linear infinite;

  @keyframes voice-prompt-spin {
    to { transform: rotate(360deg); }
  }
`;

const BAR_CSS = `
  padding: 0 1rem;
  min-height: 36px;
`;

const WAVEFORM_STYLE: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  gap: '2px',
  overflow: 'hidden',
  height: '36px',
  padding: '0 0.5rem',
};

const formatDuration = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

/**
 * Scrolling history of the microphone level. Mounted only while recording,
 * so sampling stops with the recording.
 */
const Waveform = ({ getVolume }: { getVolume: () => number }) => {
  const [history, setHistory] = useState<number[]>(() =>
    Array<number>(BAR_COUNT).fill(0),
  );

  useEffect(() => {
    const interval = setInterval(() => {
      setHistory((previous) => [...previous.slice(1), getVolume()]);
    }, SAMPLE_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [getVolume]);

  return (
    <div style={WAVEFORM_STYLE} aria-hidden="true">
      {history.map((level, index) => (
        <div
          key={index}
          style={{
            flex: 1,
            // RMS levels of speech are small: amplify them into 3-32px.
            height: `${Math.max(3, Math.min(32, level * 400))}px`,
            background:
              'var(--c--contextuals--border--semantic--brand--primary)',
            opacity: 0.3 + (index / BAR_COUNT) * 0.7,
            borderRadius: '2px',
          }}
        />
      ))}
    </div>
  );
};

interface VoicePromptBarProps {
  state: 'recording' | 'transcribing';
  elapsedSeconds: number;
  maxDurationSeconds: number;
  getVolume: () => number;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Takes over the chat input actions row while a Voice prompt is in progress. */
export const VoicePromptBar = ({
  state,
  elapsedSeconds,
  maxDurationSeconds,
  getVolume,
  onConfirm,
  onCancel,
}: VoicePromptBarProps) => {
  const { t } = useTranslation();

  if (state === 'transcribing') {
    return (
      <Box
        $direction="row"
        $align="center"
        $justify="center"
        $gap="0.5rem"
        $flex="1"
        $css={BAR_CSS}
        role="status"
        aria-label={t('Transcribing…')}
      >
        <Box $css={SPINNER_CSS} />
        <Text $size="sm" $theme="neutral" $variation="tertiary">
          {t('Transcribing…')}
        </Text>
      </Box>
    );
  }

  return (
    <Box $direction="row" $align="center" $flex="1" $css={BAR_CSS}>
      <Waveform getVolume={getVolume} />
      <Text $size="xs" $theme="neutral" $variation="tertiary">
        {`${formatDuration(elapsedSeconds)} / ${formatDuration(maxDurationSeconds)}`}
      </Text>
      <Box $direction="row" $gap="sm">
        <Button
          size="small"
          type="button"
          color="neutral"
          variant="tertiary"
          aria-label={t('Cancel recording')}
          icon={<Icon iconName="close" />}
          onClick={onCancel}
        />
        <Button
          size="small"
          type="button"
          color="neutral"
          variant="tertiary"
          aria-label={t('Confirm recording')}
          icon={<Icon iconName="check" />}
          onClick={onConfirm}
        />
      </Box>
    </Box>
  );
};
