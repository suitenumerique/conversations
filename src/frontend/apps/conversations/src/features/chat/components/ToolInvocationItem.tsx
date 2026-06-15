import { ToolInvocation } from '@ai-sdk/ui-utils';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Loader, Text } from '@/components';

import ChatBubblesIllustration from '../assets/chat-bubbles-illustration.svg';

import { DocumentParsingErrorBox } from './DocumentParsingErrorBox';

const ConversationResumeLoader = ({ t }: { t: (key: string) => string }) => {
  return (
    <Box
      $direction="column"
      $align="center"
      $gap="16px"
      $width="100%"
      $maxWidth="750px"
      $margin={{ all: 'auto', top: 'xxl', bottom: 'md' }}
    >
      <ChatBubblesIllustration />
      <Box
        $direction="column"
        $align="center"
        $gap="8px"
        $css="text-align: center; max-width: 340px;"
      >
        <Text $weight="700" $size="xl">
          {t('Picking up where you left off')}
        </Text>
        <Text
          $theme="neutral"
          $variation="secondary"
          $size="md"
          $css="line-height: 1.6;"
        >
          {t(
            'Bringing this conversation and its documents back. This may take a moment longer than usual.',
          )}
        </Text>
      </Box>
    </Box>
  );
};

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

  if (toolInvocation.toolName === 'conversation_resume') {
    if (toolInvocation.state !== 'result') {
      return <ConversationResumeLoader t={t} />;
    }

    // Intentional: success/error outcomes are handled by the modal in Chat.tsx
    return null;
  }

  if (toolInvocation.toolName === 'document_parsing') {
    if (toolInvocation.state === 'partial-call') {
      return null;
    }

    if (toolInvocation.state === 'result') {
      const result = toolInvocation.result as {
        state?: string;
        kind?: string;
        error?: string;
      };
      if (result?.state === 'error') {
        return <DocumentParsingErrorBox kind={result.kind} />;
      }
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
