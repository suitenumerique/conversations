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

    if (toolInvocation.state === 'result') {
      const result = toolInvocation.result as { state: string; error?: string };
      if (result?.state !== 'error') {
        return null;
      }
      return (
        <Box
          $direction="row"
          $align="center"
          $gap="6px"
          key={toolInvocation.toolCallId}
          $width="100%"
          $maxWidth="750px"
          $margin={{ all: 'auto', top: 'base', bottom: 'md' }}
        >
          <Text $variation="600" $size="md">
            {result.error ??
              t('An error occurred while processing the document.')}
          </Text>
        </Box>
      );
    }

    const args = toolInvocation.args as {
      documents: unknown;
      has_audio?: boolean;
    };
    const documents: unknown = args?.documents;
    const hasAudio = args?.has_audio ?? false;
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
      >
        <Loader />
        <Text $variation="600" $size="md">
          {hasAudio
            ? t('Waiting for audio transcript: {{documents}} ...', {
                documents: documentIdentifiers.join(', '),
              })
            : t('Extracting documents: {{documents}} ...', {
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
