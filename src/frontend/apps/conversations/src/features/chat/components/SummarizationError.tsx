import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';

import { RetryButton } from './RetryButton';
import { getChatErrorMessage } from './chatErrorMessages';

interface SummarizationErrorProps {
  onRetry: () => void;
}

// Rendered in the same slot as SummarizationProgress: when the summary can't
// be prepared, the progress bar is replaced in place by this failure notice
// plus a Retry button that resends the same message.
export const SummarizationError = ({ onRetry }: SummarizationErrorProps) => {
  const { t } = useTranslation();

  return (
    <Box data-testid="summarization-error" $direction="column" $gap="10px">
      <Text $variation="600" $size="md">
        {getChatErrorMessage(t, 'summarization_failed')}
      </Text>
      <Box $direction="row">
        <RetryButton onRetry={onRetry} />
      </Box>
    </Box>
  );
};
