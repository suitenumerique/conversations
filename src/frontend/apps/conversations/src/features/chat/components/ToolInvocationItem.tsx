import { ToolInvocation } from '@ai-sdk/ui-utils';
import { Loader } from '@openfun/cunningham-react';
import React from 'react';

import { Box, Text } from '@/components';

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
            <Loader size="small" />
            <Text>{`Parsing documents: ${documentIdentifiers.join(', ')} ...`}</Text>
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
      $padding={{ all: 'sm' }}
      $radius="md"
      $css="font-family: monospace; font-size: 0.9em;"
    >
      {`${toolInvocation.toolName}(${JSON.stringify(
        toolInvocation.args,
        null,
        2,
      )})`}
    </Box>
  );
};
