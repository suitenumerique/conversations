import { Button } from '@openfun/cunningham-react';
import { useRouter } from 'next/router';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';

interface ChatErrorProps {
  hasLastSubmission: boolean;
  onRetry: () => void;
}

export const ChatError = ({ hasLastSubmission, onRetry }: ChatErrorProps) => {
  const { t } = useTranslation();
  const router = useRouter();

  return (
    <Box
      $direction="column"
      $gap="6px"
      $width="100%"
      $maxWidth="750px"
      $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
      $padding={{ left: '13px' }}
    >
      <Text $variation="550" $theme="greyscale">
        {t('Sorry, an error occurred. Please try again.')}
      </Text>
      <Box
        $direction="row"
        $gap="6px"
        $align="center"
        $margin={{ top: '10px' }}
      >
        {hasLastSubmission ? (
          <Button
            size="small"
            color="tertiary"
            onClick={onRetry}
            className="retry-button"
            style={{
              color: 'var(--c--theme--colors--greyscale-550)',
              borderColor: 'var(--c--theme--colors--greyscale-300)',
            }}
            icon={
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="11"
                height="15"
                viewBox="0 0 11 15"
                fill="none"
              >
                <path
                  d="M0.733333 10.0333C0.488889 9.61111 0.305556 9.17778 0.183333 8.73333C0.0611111 8.28889 0 7.83333 0 7.36667C0 5.87778 0.516667 4.61111 1.55 3.56667C2.58333 2.52222 3.84444 2 5.33333 2H5.45L4.38333 0.933333L5.31667 0L7.98333 2.66667L5.31667 5.33333L4.38333 4.4L5.45 3.33333H5.33333C4.22222 3.33333 3.27778 3.725 2.5 4.50833C1.72222 5.29167 1.33333 6.24444 1.33333 7.36667C1.33333 7.65556 1.36667 7.93889 1.43333 8.21667C1.5 8.49444 1.6 8.76667 1.73333 9.03333L0.733333 10.0333ZM5.35 14.6667L2.68333 12L5.35 9.33333L6.28333 10.2667L5.21667 11.3333H5.33333C6.44444 11.3333 7.38889 10.9417 8.16667 10.1583C8.94444 9.375 9.33333 8.42222 9.33333 7.3C9.33333 7.01111 9.3 6.72778 9.23333 6.45C9.16667 6.17222 9.06667 5.9 8.93333 5.63333L9.93333 4.63333C10.1778 5.05556 10.3611 5.48889 10.4833 5.93333C10.6056 6.37778 10.6667 6.83333 10.6667 7.3C10.6667 8.78889 10.15 10.0556 9.11667 11.1C8.08333 12.1444 6.82222 12.6667 5.33333 12.6667H5.21667L6.28333 13.7333L5.35 14.6667Z"
                  fill="currentColor"
                />
              </svg>
            }
          >
            {t('Retry')}
          </Button>
        ) : (
          <Button
            size="small"
            color="primary"
            onClick={() => {
              void router.push('/');
            }}
            icon={<Icon iconName="add" $color="white" />}
          >
            {t('Start a new conversation')}
          </Button>
        )}
      </Box>
    </Box>
  );
};
