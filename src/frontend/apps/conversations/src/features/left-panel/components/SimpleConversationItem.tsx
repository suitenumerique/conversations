import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ChatConversation } from '@/features/chat/types';

import BubbleIcon from '../assets/bubble-bold.svg';

const ItemTextCss = css`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: initial;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
`;
const bubbleContainerStyles = css`
  background-color: transparent;
  filter: drop-shadow(0px 2px 2px rgba(0, 0, 0, 0.05));
`;
type SimpleConversationItemProps = {
  conversation: ChatConversation;
  showAccesses?: boolean;
};

export const SimpleConversationItem = memo(function SimpleConversationItem({
  conversation,
  showAccesses: _showAccesses = false,
}: SimpleConversationItemProps) {
  const { t } = useTranslation();
  const { spacingsTokens } = useCunninghamTheme();
  const title = conversation.title || t('Untitled conversation');

  return (
    <Box
      $direction="row"
      $gap={spacingsTokens.sm}
      $overflow="auto"
      className="--docs--simple-doc-item"
    >
      <Box
        $direction="row"
        $align="center"
        $css={bubbleContainerStyles}
        $padding={`${spacingsTokens['3xs']} 0`}
      >
        <BubbleIcon aria-label={t('Simple chat icon')} color="brand" />
      </Box>
      <Box $justify="center" $overflow="auto">
        <Text
          aria-describedby="doc-title"
          aria-label={title}
          $size="sm"
          $variation="850"
          $css={ItemTextCss}
        >
          {title}
        </Text>
      </Box>
    </Box>
  );
});
