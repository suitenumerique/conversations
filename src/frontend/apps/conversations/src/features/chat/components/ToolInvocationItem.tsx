import { ToolInvocation } from '@ai-sdk/ui-utils';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Loader, Text } from '@/components';

interface ToolInvocationItemProps {
  toolInvocation: ToolInvocation;
  status?: string;
  hideSearchLoader?: boolean;
}

export const ToolInvocationItem: React.FC<ToolInvocationItemProps> = ({
  toolInvocation,
  status,
  hideSearchLoader = false,
}) => {
  const { t } = useTranslation();

  if (toolInvocation.toolName === 'document_parsing') {
    if (
      toolInvocation.state === 'partial-call' ||
      toolInvocation.state === 'result'
    ) {
      return null;
    }

    const documents: unknown = (toolInvocation.args as { documents: unknown })
      ?.documents;
    const documentIdentifiers: string[] =
      Array.isArray(documents) &&
      documents.every(
        (doc): doc is { identifier: string } =>
          typeof doc === 'object' && doc !== null && 'identifier' in doc,
      )
        ? documents.map((doc) => doc.identifier)
        : [];

    return (
      <Box
        $direction="row"
        $align="center"
        $gap="6px"
        key={toolInvocation.toolCallId}
        $width="100%"
        $maxWidth="750px"
        $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
        $background="var(--c--contextuals--background--surface--tertiary)"
        $color="var(--c--contextuals--content--semantic--neutral--secondary)"
        $padding={{ all: 'sm' }}
        $radius="8px"
        $css="font-size: 0.9em; width: 100%; white-space: pre-wrap; word-wrap: break-word;"
      >
        <Loader />
        <Text $variation="600" $size="md">
          {t('Extracting documents: {{documents}} ...', {
            documents: documentIdentifiers.join(', '),
          })}
        </Text>
      </Box>
    );
  }

  return (
    <>
      {status === 'streaming' && !hideSearchLoader && (
        <Box
          $direction="row"
          $align="center"
          $gap="6px"
          key={toolInvocation.toolCallId}
          $width="100%"
          $maxWidth="750px"
          $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
        >
          <Loader />
          <Text $variation="600" $size="md">
            {t('Search...')}
          </Text>
        </Box>
      )}
    </>
  );
};
