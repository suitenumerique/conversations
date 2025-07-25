import { DateTime } from 'luxon';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import BubbleIcon from '@/assets/icons/conversation.svg';
import { Box, Icon, Text } from '@/components';
import { QuickSearchItemContent } from '@/components/quick-search/';
import { useCunninghamTheme } from '@/cunningham';
import { ChatConversation } from '@/features/chat/types';
import { useResponsiveStore } from '@/stores';

type ConversationSearchItemProps = {
  conversation: ChatConversation;
};

export const ConversationSearchItem = ({
  conversation,
}: ConversationSearchItemProps) => {
  const { isDesktop } = useResponsiveStore();
  const { spacingsTokens, colorsTokens } = useCunninghamTheme();
  const { t, i18n } = useTranslation();

  return (
    <Box
      data-testid={`doc-search-item-${conversation.id}`}
      $width="100%"
      className="--docs--doc-search-item"
    >
      <QuickSearchItemContent
        left={
          <Box $direction="row" $align="center" $gap="10px" $width="100%">
            <Box
              $direction="row"
              $flex={isDesktop ? 9 : 1}
              $gap={spacingsTokens.sm}
              $overflow="auto"
              className="--docs--simple-doc-item"
            >
              <Box
                $direction="row"
                $align="center"
                $css={css`
                  background-color: transparent;
                  filter: drop-shadow(0px 2px 2px rgba(0, 0, 0, 0.05));
                `}
                $padding={`${spacingsTokens['xs']} 0`}
              >
                <BubbleIcon
                  aria-label={t('Simple chat icon')}
                  color={colorsTokens['primary-500']}
                />
              </Box>
              <Box $justify="center" $overflow="auto">
                <Text
                  aria-describedby="doc-title"
                  aria-label={conversation.title || t('Untitled conversation')}
                  $size="sm"
                  $weight="500"
                  $variation="1000"
                >
                  {conversation.title || t('Untitled conversation')}
                </Text>
                <Text
                  $size="12px"
                  $weight="400"
                  $color="#6D778C"
                  $variation="1000"
                >
                  {conversation.updated_at
                    ? DateTime.fromISO(conversation.updated_at).toRelative({
                        locale: i18n.language,
                      })
                    : ''}
                </Text>
              </Box>
            </Box>
          </Box>
        }
        right={
          <Icon iconName="keyboard_return" $theme="primary" $variation="800" />
        }
      />
    </Box>
  );
};
