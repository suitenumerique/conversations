import { ToolInvocation } from '@ai-sdk/ui-utils';
import React from 'react';

import { Box, Loader, Text } from '@/components';

interface ToolInvocationItemProps {
  toolInvocation: ToolInvocation;
}

export const ToolInvocationItem: React.FC<ToolInvocationItemProps> = ({
  toolInvocation,
}) => {
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
        key={toolInvocation.toolCallId}
        $color="var(--c--theme--colors--greyscale-500)"
        $radius="8px"
        $css="font-size: 0.9em; font-family: inherit;"
      >
        {toolInvocation.state === 'result' ? (
          <Text $variation="600" $size="md">{`Parsing done: ${documentIdentifiers.join(', ')}`}</Text>
        ) : (
          <Box $direction="row" $gap="1rem" $align="center">
            <Loader />
            <Text $variation="600" $size="md">{`Parsing documents: ${documentIdentifiers.join(', ')} ...`}</Text>
          </Box>
        )}
      </Box>
    );
  }

  return (
    <Box
      as="pre"
      key={toolInvocation.toolCallId}
      $background="var(--c--theme--colors--greyscale-100)"
      $color="var(--c--theme--colors--greyscale-500)"
      $radius="md"
    >
      {`${toolInvocation.toolName}(${JSON.stringify(
        toolInvocation.args,
        null,
        2,
      )})`}
    </Box>
  );
};
