import { ToolInvocation } from '@ai-sdk/ui-utils';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Loader, Text } from '@/components';

import {
  getToolCardStatus,
  getToolDisplayInfo,
  getToolExpandedOutputPreview,
  getToolReadableContent,
  ToolCardStatus,
} from './toolCardUtils';

const CARD_CSS = `
  width: fit-content;
  max-width: 100%;
`;

const HEADER_BUTTON_CSS = `
  width: fit-content;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  padding: 0;
`;

const DETAIL_TEXT_CSS = `
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
`;

const STATUS_COLORS: Record<Exclude<ToolCardStatus, 'running'>, string> = {
  completed: 'var(--c--contextuals--content--semantic--success--primary)',
  error: 'var(--c--contextuals--content--semantic--error--primary)',
};

interface ToolCardProps {
  toolInvocation: ToolInvocation;
}

const StatusIndicator = ({ status }: { status: ToolCardStatus }) => {
  if (status === 'running') {
    return <Loader size={14} />;
  }

  return (
    <Icon
      iconName={status === 'completed' ? 'check_circle' : 'error'}
      $size="14px"
      $css={`color: ${STATUS_COLORS[status]};`}
      aria-hidden="true"
    />
  );
};

export const ToolCard: React.FC<ToolCardProps> = ({ toolInvocation }) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = React.useState(false);
  const status = getToolCardStatus(toolInvocation);
  const displayInfo = getToolDisplayInfo(toolInvocation.toolName);
  const output =
    toolInvocation.state === 'result' ? toolInvocation.result : undefined;
  const readableContent = getToolReadableContent(
    toolInvocation.toolName,
    toolInvocation.args,
    output,
    t,
  );
  const expandedOutputPreview = getToolExpandedOutputPreview(
    toolInvocation.toolName,
    output,
    t,
  );

  const hasDetails = Boolean(
    readableContent.inputPreview ||
      readableContent.outputPreview ||
      readableContent.errorPreview ||
      expandedOutputPreview,
  );

  return (
    <Box
      data-testid={`tool-card-${toolInvocation.toolCallId}`}
      $css={CARD_CSS}
      $margin={{ top: '4px', bottom: '4px' }}
    >
      <Box
        as="button"
        type="button"
        aria-expanded={expanded}
        aria-label={t('Toggle tool details')}
        onClick={() => hasDetails && setExpanded((current) => !current)}
        $css={HEADER_BUTTON_CSS}
        $cursor={hasDetails ? 'pointer' : 'default'}
      >
        <Box $direction="row" $align="center" $gap="6px" $minWidth="0">
          <StatusIndicator status={status} />
          <Text
            $size="xs"
            $weight="600"
            $theme="greyscale"
            $variation="700"
            $css="line-height: 1.3; white-space: nowrap;"
          >
            {displayInfo.label}
          </Text>
          {hasDetails && (
            <Icon
              iconName={expanded ? 'expand_less' : 'expand_more'}
              $size="16px"
              $theme="greyscale"
              $variation="550"
              aria-hidden="true"
            />
          )}
        </Box>
      </Box>

      {expanded && hasDetails && (
        <Box
          $direction="column"
          $gap="6px"
          $padding={{ left: '20px', top: '4px', bottom: '4px' }}
        >
          {readableContent.inputPreview && (
            <Box $direction="column" $gap="2px">
              <Text $size="xs" $weight="600" $theme="greyscale" $variation="600">
                {readableContent.inputLabel}
              </Text>
              <Text $size="xs" $theme="greyscale" $variation="700" $css={DETAIL_TEXT_CSS}>
                {readableContent.inputPreview}
              </Text>
            </Box>
          )}

          {readableContent.errorPreview && (
            <Text $size="xs" $theme="error" $variation="primary" $css={DETAIL_TEXT_CSS}>
              {readableContent.errorPreview}
            </Text>
          )}

          {expandedOutputPreview && !readableContent.errorPreview && (
            <Box $direction="column" $gap="2px">
              <Text $size="xs" $weight="600" $theme="greyscale" $variation="600">
                {t('Preview')}
              </Text>
              <Text $size="xs" $theme="greyscale" $variation="700" $css={DETAIL_TEXT_CSS}>
                {expandedOutputPreview}
              </Text>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
};
