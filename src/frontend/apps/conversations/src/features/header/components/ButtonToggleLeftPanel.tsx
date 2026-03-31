import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/router';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import LeftPanelIcon from '@/assets/icons/left-panel-bold.svg';
import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import {
  getConversation,
  KEY_CONVERSATION,
} from '@/features/chat/api/useConversation';
import { useInfiniteProjects } from '@/features/chat/api/useProjects';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import {
  PROJECT_COLORS,
  PROJECT_ICONS,
} from '@/features/left-panel/components/projects/project-constants';

const conversationTitleCss = css`
  display: block;
  color: var(--c--contextuals--content--semantic--neutral--primary);
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  z-index: 100;
`;

export const ButtonToggleLeftPanel = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { colorsTokens } = useCunninghamTheme();
  const { data: projects } = useInfiniteProjects({ page: 1, page_size: 100 });
  const { isPanelOpen, togglePanel } = useChatPreferencesStore();
  const currentConversationId =
    typeof router.query.id === 'string' ? router.query.id : undefined;
  const { data: currentConversation } = useQuery({
    queryKey: [KEY_CONVERSATION, currentConversationId],
    queryFn: () => {
      if (currentConversationId === undefined) {
        return Promise.reject(new Error('Conversation id required'));
      }
      return getConversation({ id: currentConversationId });
    },
    enabled: !!currentConversationId,
  });

  const projectForCurrentConversation = useMemo(() => {
    if (!currentConversationId) {
      return undefined;
    }

    return projects?.pages
      .flatMap((page) => page.results)
      .find((project) =>
        project.conversations.some((conv) => conv.id === currentConversationId),
      );
  }, [projects?.pages, currentConversationId]);

  const currentConversationTitle = useMemo(() => {
    if (!currentConversationId) {
      return '';
    }
    if (currentConversation?.title) {
      return currentConversation.title;
    }

    return projectForCurrentConversation
      ? projectForCurrentConversation.conversations.find(
          (conv) => conv.id === currentConversationId,
        )?.title || t('Untitled conversation')
      : t('Untitled conversation');
  }, [
    currentConversationId,
    currentConversation?.title,
    projectForCurrentConversation,
    t,
  ]);

  const projectIconName =
    projectForCurrentConversation?.icon ?? currentConversation?.project?.icon;
  const ProjectIcon = projectIconName
    ? (PROJECT_ICONS[projectIconName] ?? undefined)
    : undefined;
  const projectIconColor = projectForCurrentConversation?.color
    ? (colorsTokens[
        PROJECT_COLORS[
          projectForCurrentConversation.color
        ] as keyof typeof colorsTokens
      ] ?? undefined)
    : undefined;

  return (
    <Box $direction="row" $align="center" $gap="4px">
      <Button
        size="small"
        onClick={() => togglePanel()}
        aria-label={
          isPanelOpen ? t('Close the left panel') : t('Open the left panel')
        }
        color="neutral"
        variant="tertiary"
        icon={<LeftPanelIcon />}
      ></Button>
      {currentConversationTitle && !isPanelOpen && (
        <Box
          $direction="row"
          $align="center"
          $gap="6px"
          $margin={{ right: '8px' }}
        >
          {ProjectIcon && (
            <Box
              $display="flex"
              $align="center"
              $justify="center"
              style={{ color: projectIconColor }}
            >
              <ProjectIcon
                width={20}
                height={20}
                style={{ fill: 'currentColor' }}
              />
            </Box>
          )}
          <Text
            $size="sm"
            $variation="primary"
            $weight="700"
            $css={conversationTitleCss}
            title={currentConversationTitle}
          >
            {currentConversationTitle}
          </Text>
        </Box>
      )}
    </Box>
  );
};
