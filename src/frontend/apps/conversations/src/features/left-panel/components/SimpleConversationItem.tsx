import { DateTime } from 'luxon';
import { memo, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ChatConversation } from '@/features/chat/types';

const ItemTextCss = css`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: initial;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
`;

const descriptionCss = css`
  color: var(--c--contextuals--content--semantic--neutral--tertiary);
  font-weight: 400;
`;

type SimpleConversationItemProps = {
  conversation: ChatConversation;
  showAccesses?: boolean;
  showUpdatedAt?: boolean;
};

export const SimpleConversationItem = memo(function SimpleConversationItem({
  conversation,
  showAccesses: _showAccesses = false,
  showUpdatedAt = false,
}: SimpleConversationItemProps) {
  const { t, i18n } = useTranslation();
  const { spacingsTokens } = useCunninghamTheme();
  const title = conversation.title || t('Untitled conversation');

  const updatedAtLabel = useMemo(() => {
    if (!showUpdatedAt || !conversation.updated_at) {
      return null;
    }
    const dt = DateTime.fromISO(conversation.updated_at);
    if (!dt.isValid) {
      return null;
    }
    return dt.toRelative({ locale: i18n.language });
  }, [showUpdatedAt, conversation.updated_at, i18n.language]);

  return (
    <Box
      $direction="row"
      $gap={spacingsTokens.sm}
      $overflow="auto"
      $justify="space-between"
      $align="center"
      className="--docs--simple-doc-item"
    >
      <Box
        $direction="row"
        $gap={spacingsTokens.sm}
        $overflow="auto"
        $shrink={1}
      >
        <Box $justify="center" $overflow="auto">
          <Text
            aria-label={title}
            $size="sm"
            $variation="primary"
            $weight="400"
            $css={ItemTextCss}
          >
            {title}
          </Text>
        </Box>
      </Box>
      {updatedAtLabel && (
        <Text $size="xs" $variation="tertiary" $css={descriptionCss}>
          {updatedAtLabel}
        </Text>
      )}
    </Box>
  );
});
