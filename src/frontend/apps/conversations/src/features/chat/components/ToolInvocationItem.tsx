import { ToolInvocation } from '@ai-sdk/ui-utils';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';

import ChatBubblesIllustration from '../assets/chat-bubbles-illustration.svg';

import { DocumentParsingErrorBox } from './DocumentParsingErrorBox';
import { ToolCard } from './ToolCard';
import { getDocumentParsingSummary } from './toolCardUtils';

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
}

export const isVisibleToolInvocation = (
  toolInvocation: ToolInvocation,
): boolean => {
  if (toolInvocation.toolName === 'conversation_resume') {
    return toolInvocation.state !== 'result';
  }

  if (toolInvocation.toolName === 'document_parsing') {
    if (toolInvocation.state === 'partial-call') {
      return false;
    }

    if (toolInvocation.state === 'result') {
      const result = toolInvocation.result as { state?: string };
      return result?.state === 'error';
    }

    return true;
  }

  return true;
};

export const ToolInvocationItem: React.FC<ToolInvocationItemProps> = ({
  toolInvocation,
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

    const documentSummary = getDocumentParsingSummary(toolInvocation.args);
    const toolInvocationWithSummary = documentSummary
      ? {
          ...toolInvocation,
          args: {
            ...toolInvocation.args,
            documents: documentSummary,
          },
        }
      : toolInvocation;

    return <ToolCard toolInvocation={toolInvocationWithSummary} />;
  }

  return <ToolCard toolInvocation={toolInvocation} />;
};
