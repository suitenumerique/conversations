import { useRouter } from 'next/router';
import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Icon, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';
import { ChatProject } from '@/features/chat/types';
import { ConversationItemActions } from '@/features/left-panel/components/ConversationItemActions';
import { ConversationRow } from '@/features/left-panel/components/ConversationRow';
import { ProjectItemActions } from '@/features/left-panel/components/projects/ProjectItemActions';
import {
  PROJECT_COLORS,
  PROJECT_ICONS,
} from '@/features/left-panel/components/projects/project-constants';
import { useResponsiveStore } from '@/stores';

type LeftPanelProjectItemProps = {
  project: ChatProject;
  currentConversationId?: string;
};

const headerStyles = css`
  border-radius: 4px;
  width: 100%;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s cubic-bezier(1, 0, 0, 1);
  .pinned-actions {
    opacity: 0;
    transition: opacity 0.3s cubic-bezier(1, 0, 0, 1);
  }
  &:hover,
  &:focus-within {
    background-color: var(
      --c--contextuals--background--semantic--overlay--primary
    );
    .pinned-actions {
      opacity: 1;
    }
  }

  @media (width <= 768px) {
    &[data-project-open='true'] {
      .pinned-actions {
        opacity: 1;
      }
    }
  }
`;

const conversationListStyles = css`
  margin-top: 2px;
  overflow: hidden;
`;

const titleTextStyles = css`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: initial;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
`;

const titleStyles = css`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: initial;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  padding-left: 24px;
`;

const arrowButtonStyles = css`
  border: none;
  background: transparent;
  padding: 0;
  margin: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
`;

export const LeftPanelProjectItem = memo(function LeftPanelProjectItem({
  project,
  currentConversationId,
}: LeftPanelProjectItemProps) {
  const { t } = useTranslation();
  const { colorsTokens } = useCunninghamTheme();
  const router = useRouter();
  const setProjectId = usePendingChatStore((s) => s.setProjectId);
  const { isDesktop } = useResponsiveStore();
  const { setPanelOpen } = useChatPreferencesStore();

  const [isOpen, setIsOpen] = useState(false);

  const belongsToProject =
    currentConversationId &&
    project.conversations.some((c) => c.id === currentConversationId);

  useEffect(() => {
    if (belongsToProject) {
      setIsOpen(true);
    }
  }, [belongsToProject]);

  const IconComponent = PROJECT_ICONS[project.icon] ?? PROJECT_ICONS.folder;
  const iconColor =
    colorsTokens[PROJECT_COLORS[project.color] as keyof typeof colorsTokens] ??
    undefined;

  const toggleOpen = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  const handleNewConversation = useCallback(() => {
    setProjectId(project.id);
    void router.push('/chat/');
    if (!isDesktop) {
      setPanelOpen(false);
    }
  }, [router, project.id, setProjectId, isDesktop, setPanelOpen]);

  return (
    <Box>
      <Box
        $direction="row"
        $align="center"
        $padding={{ horizontal: 'xs', vertical: '4px' }}
        $gap="2px"
        $justify="space-between"
        $css={headerStyles}
        data-project-open={isOpen ? 'true' : 'false'}
      >
        <Box
          $direction="row"
          $align="center"
          $gap="2px"
          $css="min-width: 0; flex: 1;"
        >
          <Box
            as="button"
            type="button"
            onClick={toggleOpen}
            aria-expanded={isOpen}
            aria-label={`Toggle conversations for ${project.title}`}
            disabled={project.conversations.length === 0}
            $css={arrowButtonStyles}
          >
            <Icon
              iconName={
                isOpen && project.conversations.length > 0
                  ? 'expand_more'
                  : 'chevron_right'
              }
              $theme="neutral"
              $variation="tertiary"
              $size="18px"
              $css={`opacity: ${project.conversations.length === 0 ? '0' : '1'};`}
            />
          </Box>

          <Box
            $display="flex"
            $align="center"
            $justify="center"
            $width="18px"
            $height="18px"
            style={{ color: iconColor, marginRight: '4px', flexShrink: 0 }}
          >
            <IconComponent
              width={18}
              height={18}
              style={{ fill: 'currentColor', display: 'block' }}
            />
          </Box>
          <Box
            as="button"
            type="button"
            onClick={handleNewConversation}
            aria-label={`Start new conversation in ${project.title}`}
            $css={css`
              ${titleTextStyles}
              border: none;
              background: transparent;
              padding: 0;
              margin: 0;
              width: 100%;
              text-align: left;
              cursor: pointer;
              font: inherit;
              color: inherit;
            `}
          >
            <Text
              $css={css`
                ${titleTextStyles}
              `}
              $size="sm"
              $variation="primary"
              $weight={isOpen ? '700' : '500'}
            >
              {project.title}
            </Text>
          </Box>
        </Box>

        <div
          className="pinned-actions"
          role="presentation"
          style={{ display: 'flex', alignItems: 'center', gap: '2px' }}
        >
          <ProjectItemActions project={project} />
        </div>
      </Box>

      {/* Conversations list */}
      {isOpen && (
        <Box $padding={{ left: '0px' }} $css={conversationListStyles}>
          {project.conversations.length > 0 &&
            project.conversations.map((conv) => (
              <ConversationRow
                key={conv.id}
                conversationId={conv.id}
                isActive={conv.id === currentConversationId}
                actions={<ConversationItemActions conversation={conv} />}
              >
                <Text
                  $css={titleStyles}
                  $size="sm"
                  $variation="primary"
                  $weight="400"
                >
                  {conv.title || t('Untitled conversation')}
                </Text>
              </ConversationRow>
            ))}
        </Box>
      )}
    </Box>
  );
});
