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
    if (toolInvocation.state === 'partial-call') {
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
        as="pre"
        key={toolInvocation.toolCallId}
        $background="var(--c--theme--colors--greyscale-100)"
        $color="var(--c--theme--colors--greyscale-500)"
        $padding={{ all: 'sm' }}
        $radius="8px"
        $css="font-size: 0.9em;"
      >
        {toolInvocation.state === 'result' ? (
          <Text>{`Parsing done: ${documentIdentifiers.join(', ')}`}</Text>
        ) : (
          <Box $direction="row" $gap="1rem" $align="center">
            <Loader />
            <Text>{`Parsing documents: ${documentIdentifiers.join(', ')} ...`}</Text>
          </Box>
        )}
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
            {toolInvocation.toolName === 'summarize' ? t('Summarizing...') : t('Search...')}
          </Text>
        </Box>
      )}
    </>
  );
};
