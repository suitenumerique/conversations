import { DateTime } from 'luxon';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ChatConversation } from '@/features/chat/types';
import { useResponsiveStore } from '@/stores';

import SimpleFileIcon from '../assets/simple-document.svg';

const ItemTextCss = css`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: initial;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
`;

type SimpleConversationItemProps = {
  conversation: ChatConversation;
  showAccesses?: boolean;
};

export const SimpleConversationItem = ({
  conversation,
  showAccesses = false,
}: SimpleConversationItemProps) => {
  const { t } = useTranslation();
  const { spacingsTokens, colorsTokens } = useCunninghamTheme();
  const { isDesktop } = useResponsiveStore();

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
        $css={css`
          background-color: transparent;
          filter: drop-shadow(0px 2px 2px rgba(0, 0, 0, 0.05));
        `}
        $padding={`${spacingsTokens['3xs']} 0`}
      >
        <SimpleFileIcon
          aria-label={t('Simple document icon')}
          color={colorsTokens['primary-500']}
        />
      </Box>
      <Box $justify="center" $overflow="auto">
        <Text
          aria-describedby="doc-title"
          aria-label={conversation.title || t('Untitled conversation')}
          $size="sm"
          $variation="1000"
          $weight="500"
          $css={ItemTextCss}
        >
          {conversation.title || t('Untitled conversation')}
        </Text>
        {(!isDesktop || showAccesses) && (
          <Box
            $direction="row"
            $align="center"
            $gap={spacingsTokens['3xs']}
            $margin={{ top: '-2px' }}
          >
            <Text $variation="600" $size="xs">
              {DateTime.fromISO(conversation.updated_at).toRelative()}
            </Text>
          </Box>
        )}
      </Box>
    </Box>
  );
};
