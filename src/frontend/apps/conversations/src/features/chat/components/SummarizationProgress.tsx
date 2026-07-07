import React from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';

// Fake, purely time-based progress (the backend reports no real progress):
// 1 - e^(-t/τ), capped below 100% until the summarization actually completes.
const TIME_CONSTANT_MS = 8000;
const MAX_RATIO = 0.95;
const TICK_MS = 100;
const HIDE_DELAY_MS = 400;

interface SummarizationProgressProps {
  done: boolean;
}

export const SummarizationProgress = ({ done }: SummarizationProgressProps) => {
  const { t } = useTranslation();
  const [progress, setProgress] = React.useState(0);
  const [hidden, setHidden] = React.useState(false);

  React.useEffect(() => {
    if (done) {
      return;
    }
    const startedAt = Date.now();
    const interval = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      setProgress(MAX_RATIO * (1 - Math.exp(-elapsed / TIME_CONSTANT_MS)));
    }, TICK_MS);
    return () => clearInterval(interval);
  }, [done]);

  React.useEffect(() => {
    if (!done) {
      return;
    }
    setProgress(1);
    const timeout = setTimeout(() => setHidden(true), HIDE_DELAY_MS);
    return () => clearTimeout(timeout);
  }, [done]);

  if (hidden) {
    return null;
  }

  return (
    <Box
      data-testid="summarization-progress"
      $direction="column"
      $gap="6px"
      $width="100%"
    >
      <Text $variation="600" $size="md">
        {t('Summarizing conversation...')}
      </Text>
      <Box
        $width="100%"
        $css="height: 4px; border-radius: 2px; background: var(--c--globals--colors--gray-200); overflow: hidden;"
      >
        <Box
          data-testid="summarization-progress-fill"
          style={{ width: `${Math.round(progress * 100)}%` }}
          $css={`
            height: 100%;
            border-radius: 2px;
            background: var(--c--globals--colors--brand-600);
            transition: width ${TICK_MS * 2}ms linear;
          `}
        />
      </Box>
    </Box>
  );
};
