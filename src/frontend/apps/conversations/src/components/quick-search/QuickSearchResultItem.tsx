import { DateTime } from 'luxon';
import { memo, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ChatConversation } from '@/features/chat/types';

import ArrowForwardIcon from './assets/arrow-forward.svg';
import BubbleIcon from './assets/bubble.svg';

const descriptionCss = css`
  color: var(--c--contextuals--content--semantic--neutral--tertiary);
  font-weight: 400;
`;

type QuickSearchResultItemProps = {
  conversation: ChatConversation;
};

export const QuickSearchResultItem = memo(function QuickSearchResultItem({
  conversation,
}: QuickSearchResultItemProps) {
  const { t, i18n } = useTranslation();
  const { spacingsTokens } = useCunninghamTheme();
  const title = conversation.title || t('Untitled conversation');

  const updatedAtLabel = useMemo(() => {
    if (!conversation.updated_at) {
      return null;
    }
    const dt = DateTime.fromISO(conversation.updated_at);
    if (!dt.isValid) {
      return null;
    }
    return dt.toRelative({ locale: i18n.language });
  }, [conversation.updated_at, i18n.language]);

  return (
    <Box
      $direction="row"
      $align="center"
      $gap={spacingsTokens.sm}
      $width="100%"
      $padding={{ vertical: 'xxs', horizontal: 'xs' }}
    >
      <BubbleIcon aria-hidden="true" color="brand" />
      <Box $flex={1} $direction="column" $minWidth={0}>
        <Text aria-label={title} $size="sm" $shrink={1}>
          {title}
        </Text>
        {updatedAtLabel && (
          <Text $css={descriptionCss} $size="xs" $theme="greyscale" $shrink={0}>
            {updatedAtLabel}
          </Text>
        )}
      </Box>
      <Box
        className="show-right-on-focus"
        $shrink={0}
        $css="color: var(--c--contextuals--content--semantic--brand--primary);"
      >
        <ArrowForwardIcon aria-hidden width={18} height={12} />
      </Box>
    </Box>
  );
});
