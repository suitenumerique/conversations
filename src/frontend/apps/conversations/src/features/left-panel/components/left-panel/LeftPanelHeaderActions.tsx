import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import NewChatIcon from '@/assets/icons/new-message-bold.svg';
import FolderPlusIcon from '@/assets/icons/uikit-custom/folder-plus.svg';
import { Box, Icon } from '@/components';

import { LeftPanelMenuItem } from './LeftPanelMenuItem';

const iconWrapperCss = css`
  color: var(--c--contextuals--content--semantic--neutral--secondary);
  & svg {
    fill: currentColor;
  }
  .material-symbols-outlined,
  .material-symbols {
    color: inherit;
  }
`;

type LeftPanelHeaderActionsProps = {
  onNewChat: () => void;
  onSearch: () => void;
  onCreateProject: () => void;
};

export const LeftPanelHeaderActions = ({
  onNewChat,
  onSearch,
  onCreateProject,
}: LeftPanelHeaderActionsProps) => {
  const { t } = useTranslation();

  return (
    <Box
      $direction="column"
      $gap="2px"
      $align="center"
      $margin={{ top: 'base' }}
      $padding={{ horizontal: 'sm' }}
    >
      <LeftPanelMenuItem
        icon={
          <Box $css={iconWrapperCss} $display="flex" $align="center">
            <NewChatIcon width="24" height="24" aria-hidden />
          </Box>
        }
        label={t('New chat')}
        onClick={onNewChat}
        aria-label={t('New chat')}
      />
      <LeftPanelMenuItem
        icon={
          <Box $css={iconWrapperCss} $display="flex" $align="center">
            <Icon iconName="search" aria-hidden />
          </Box>
        }
        label={t('Search for a chat')}
        onClick={onSearch}
        aria-label={t('Search for a chat')}
      />
      <LeftPanelMenuItem
        icon={
          <Box $css={iconWrapperCss} $display="flex" $align="center">
            <FolderPlusIcon aria-hidden width="24" height="24" />
          </Box>
        }
        label={t('New project')}
        onClick={onCreateProject}
        aria-label={t('New project')}
      />
    </Box>
  );
};
