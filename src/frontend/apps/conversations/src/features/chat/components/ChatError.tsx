import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useRouter } from 'next/router';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import { useConfig } from '@/core';

import { RetryButton } from './RetryButton';
import { getChatErrorMessage } from './chatErrorMessages';

export type ChatErrorType =
  | 'generic'
  | 'model_unavailable'
  | 'model_rate_limited'
  | 'model_connection_error'
  | 'model_not_found'
  | 'model_wrong_type'
  | 'model_busy'
  | 'summarization_failed';

interface ChatErrorProps {
  errorType: ChatErrorType;
  hasLastSubmission: boolean;
  onRetry: () => void;
}

export const ChatError = ({
  errorType,
  hasLastSubmission,
  onRetry,
}: ChatErrorProps) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { data: config } = useConfig();
  const statusPageUrl = config?.STATUS_PAGE_URL;
  const isProviderError = errorType !== 'generic';
  const showStatusLink = new Set<ChatErrorType>([
    'model_unavailable',
    'model_rate_limited',
    'model_connection_error',
    'model_busy',
  ]).has(errorType);

  return (
    <Box
      $direction="column"
      $gap="6px"
      $width="100%"
      $maxWidth="var(--chat-content-max-width, 750px)"
      $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
      $padding={{ left: '13px' }}
    >
      {isProviderError ? (
        <Box $direction="row" $gap="12px" $align="center">
          <Text $variation="700" $size="1.375rem" $theme="greyscale">
            {getChatErrorMessage(t, errorType)}
          </Text>
          {statusPageUrl && showStatusLink && (
            <a
              href={statusPageUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={t('Check service status')}
              style={{
                color:
                  'var(--c--contextuals--content--semantic--greyscale--700)',
                display: 'inline-flex',
                textDecoration: 'none',
              }}
            >
              <Icon iconName="info" $size="1.375rem" $withThemeInherited />
            </a>
          )}
        </Box>
      ) : (
        <Text $variation="550" $theme="greyscale">
          {getChatErrorMessage(t, errorType)}
        </Text>
      )}
      <Box
        $direction="row"
        $gap="6px"
        $align="center"
        $margin={{ top: '10px' }}
      >
        {!isProviderError && <RetryButton onRetry={onRetry} />}
        {!isProviderError && !hasLastSubmission && (
          <Button
            size="nano"
            color="brand"
            variant="bordered"
            onClick={() => {
              void router.push('/');
            }}
            icon={<Icon iconName="add" $color="greyscale" />}
          >
            {t('Start a new conversation')}
          </Button>
        )}
      </Box>
    </Box>
  );
};
