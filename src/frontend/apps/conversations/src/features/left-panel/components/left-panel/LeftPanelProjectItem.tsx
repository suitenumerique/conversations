import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useRouter } from 'next/router';
import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Icon, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';
import { ChatProject } from '@/features/chat/types';
import { ConversationItemActions } from '@/features/left-panel/components/ConversationItemActions';
import { ConversationRow } from '@/features/left-panel/components/ConversationRow';
import { ProjectItemActions } from '@/features/left-panel/components/projects/ProjectItemActions';
import {
  PROJECT_COLORS,
  PROJECT_ICONS,
} from '@/features/left-panel/components/projects/project-constants';
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
`;

const conversationListStyles = css`
  overflow: hidden;
`;

const titleTextStyles = css`
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const LeftPanelProjectItem = memo(function LeftPanelProjectItem({
  project,
  currentConversationId,
}: LeftPanelProjectItemProps) {
  const { t } = useTranslation();
  const { colorsTokens } = useCunninghamTheme();
  const router = useRouter();
  const pendingProjectId = usePendingChatStore((s) => s.projectId);
  const setProjectId = usePendingChatStore((s) => s.setProjectId);

  const [isOpen, setIsOpen] = useState(false);

  // Auto-open when current conversation belongs to this project or creating a new one in it
  const belongsToProject =
    currentConversationId &&
    project.conversations.some((c) => c.id === currentConversationId);
  const isTargetProject = belongsToProject || pendingProjectId === project.id;

  useEffect(() => {
    if (isTargetProject) {
      setIsOpen(true);
    }
  }, [isTargetProject]);

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
  }, [router, project.id, setProjectId]);

  return (
    <Box>
      {/* Project header */}
      <Box
        $direction="row"
        $align="center"
        $padding={{ horizontal: 'xs', vertical: '4px' }}
        $gap="2px"
        $justify="space-between"
        $css={headerStyles}
      >
        <Box
          $direction="row"
          $align="center"
          $gap="2px"
          $css="min-width: 0; flex: 1; cursor: pointer;"
          role="button"
          tabIndex={0}
          aria-expanded={isOpen}
          aria-label={project.title}
          onClick={toggleOpen}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              toggleOpen();
            }
          }}
        >
          <Icon
            iconName={isOpen ? 'keyboard_arrow_down' : 'keyboard_arrow_right'}
            $theme="greyscale"
            $variation="600"
            $size="18px"
          />

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
          <Text
            $size="sm"
            $variation="primary"
            $weight="500"
            $css={titleTextStyles}
          >
            {project.title}
          </Text>
        </Box>

        <div
          className="pinned-actions"
          role="presentation"
          style={{ display: 'flex', alignItems: 'center', gap: 0 }}
        >
          <ProjectItemActions project={project} />
          <Button
            aria-label={t('New conversation in project')}
            onClick={handleNewConversation}
            color="info"
            variant="bordered"
            size="nano"
            icon={<Icon iconName="add" $size="18px" $theme="primary" />}
          />
        </div>
      </Box>

      {/* Conversations list */}
      {isOpen && (
        <Box $padding={{ left: '28px' }} $css={conversationListStyles}>
          {project.conversations.length === 0 ? (
            <Text
              $size="xs"
              $variation="tertiary"
              $padding={{ horizontal: 'xs', vertical: '4px' }}
            >
              {t('No conversations')}
            </Text>
          ) : (
            project.conversations.map((conv) => (
              <ConversationRow
                key={conv.id}
                conversationId={conv.id}
                isActive={conv.id === currentConversationId}
                actions={<ConversationItemActions conversation={conv} />}
              >
                <Text $size="sm" $variation="primary" $weight="400">
                  {conv.title || t('Untitled conversation')}
                </Text>
              </ConversationRow>
            ))
          )}
        </Box>
      )}
    </Box>
  );
});
