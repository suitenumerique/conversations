import { memo, useCallback, useState } from 'react';
import { css } from 'styled-components';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ChatProject } from '@/features/chat/types';
import { ConversationItemActions } from '@/features/left-panel/components/ConversationItemActions';
import { ConversationRow } from '@/features/left-panel/components/ConversationRow';
import { PROJECT_COLORS, PROJECT_ICONS } from '@/features/left-panel/components/project-constants';
import { ProjectItemActions } from '@/features/left-panel/components/ProjectItemActions';
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

  const [isOpen, setIsOpen] = useState(false);

  const iconColor =
    colorsTokens[PROJECT_COLORS[project.color] as keyof typeof colorsTokens] ??
    undefined;

  const toggleOpen = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  return (
    <Box>
      {/* Project header - click to toggle */}
      <Box
        $direction="row"
        $align="center"
        $padding={{ horizontal: 'xs', vertical: '4px' }}
        $gap="2px"
        $justify="space-between"
        $css={headerStyles}
        onClick={toggleOpen}
        role="button"
        aria-expanded={isOpen}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggleOpen();
          }
        }}
      >
        <Box $direction="row" $align="center" $gap="2px" $css="min-width: 0;">
          <Icon
            iconName={isOpen ? 'keyboard_arrow_down' : 'keyboard_arrow_right'}
            $theme="greyscale"
            $variation="600"
            $size="18px"
          />

          {(() => {
            const IconComp = PROJECT_ICONS[project.icon] ?? PROJECT_ICONS.folder;
            return (
              <Box
                $display="flex"
                $align="center"
                $justify="center"
                $width="18px"
                $height="18px"
                style={{ color: iconColor, marginRight: '4px', flexShrink: 0 }}
              >
                <IconComp width={18} height={18} style={{ fill: 'currentColor', display: 'block' }} />
              </Box>
            );
          })()}
          <Text
            aria-label={project.title}
            $size="sm"
            $variation="primary"
            $weight="500"
            $css={titleTextStyles}
          >
            {project.title}
          </Text>
        </Box>

        <Box
          className="pinned-actions"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <ProjectItemActions project={project} />
        </Box>
      </Box>

      {/* Conversations list */}
      {isOpen && (
        <Box $padding={{ left: 'sm' }} $css={conversationListStyles}>
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
