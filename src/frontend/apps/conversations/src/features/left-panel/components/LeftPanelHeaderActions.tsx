import { css } from 'styled-components';
import { useTranslation } from 'react-i18next';

import NewChatIcon from '@/assets/icons/new-message-bold.svg';
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
};

export const LeftPanelHeaderActions = ({
  onNewChat,
  onSearch,
}: LeftPanelHeaderActionsProps) => {
  const { t } = useTranslation();

  return (
    <Box
      $direction="column"
      $gap="2px"
      $align="center"
      $margin={{ vertical: 'base' }}
      $padding={{ horizontal: 'sm' }}
    >
      <LeftPanelMenuItem
        icon={
          <Box $css={iconWrapperCss} $display="flex" $align="center">
            <NewChatIcon aria-hidden />
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
    </Box>
  );
};
