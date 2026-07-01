import React from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import { useConfig } from '@/core';

import {
  STATUS_LINK_KINDS,
  getDocumentParsingErrorMessage,
} from './documentParsingErrorMessages';

interface DocumentParsingErrorBoxProps {
  kind?: string;
}

export const DocumentParsingErrorBox: React.FC<
  DocumentParsingErrorBoxProps
> = ({ kind }) => {
  const { t } = useTranslation();
  const { data: config } = useConfig();
  const statusPageUrl = config?.STATUS_PAGE_URL;

  const showStatusLink =
    !!statusPageUrl && !!kind && STATUS_LINK_KINDS.has(kind);

  return (
    <Box
      $direction="row"
      $align="center"
      $gap="6px"
      $width="100%"
      $maxWidth="750px"
      $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
      $padding={{ left: '13px' }}
    >
      <Text $variation="550" $theme="greyscale">
        {getDocumentParsingErrorMessage(t, kind)}
      </Text>
      {showStatusLink && (
        <a
          href={statusPageUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={t('Check service status')}
        >
          <Icon iconName="info" $size="1rem" $color="greyscale" />
        </a>
      )}
    </Box>
  );
};
