import { memo, useCallback, useMemo, type ReactNode } from 'react';
import { css } from 'styled-components';

import { Box, StyledLink } from '@/components';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { useResponsiveStore } from '@/stores';

type ConversationRowProps = {
  conversationId: string;
  isActive: boolean;
  children: ReactNode;
  actions?: ReactNode;
};

const linkStyles = css`
  overflow: auto;
  flex-grow: 1;
  color: var(--c--theme--colors--greyscale-900);
`;

const getBoxStyles = (isActive: boolean, isDesktop: boolean) => css`
  border-radius: 4px;
  width: 100%;
  margin-bottom: 1px;
  background-color: ${isActive
    ? 'var(--c--contextuals--background--semantic--overlay--primary)'
    : ''};
  font-weight: ${isActive ? '700' : '500'};
  transition: background-color 0.2s cubic-bezier(1, 0, 0, 1);
  .pinned-actions {
    padding: 2px 0;
    opacity: ${isDesktop ? 0 : 1};
    background-color: transparent;
    transition: all 0.3s cubic-bezier(1, 0, 0, 1);
  }
  &:hover,
  &:focus,
  &:focus-within {
    background-color: var(
      --c--contextuals--background--semantic--overlay--primary
    );
    .pinned-actions {
      opacity: 1;
    }
  }
  .pinned-actions:focus-within {
    opacity: 1;
  }
`;

const containerPadding = { horizontal: 'xs', vertical: '4px' };

export const ConversationRow = memo(function ConversationRow({
  conversationId,
  isActive,
  children,
  actions,
}: ConversationRowProps) {
  const isDesktop = useResponsiveStore((state) => state.isDesktop);
  const setPanelOpen = useChatPreferencesStore((state) => state.setPanelOpen);

  const handleLinkClick = useCallback(() => {
    if (!isDesktop) {
      setPanelOpen(false);
    }
  }, [isDesktop, setPanelOpen]);

  const boxStyles = useMemo(
    () => getBoxStyles(isActive, isDesktop),
    [isActive, isDesktop],
  );

  return (
    <Box
      $direction="row"
      $align="center"
      $padding={containerPadding}
      $justify="space-between"
      $css={boxStyles}
    >
      <StyledLink
        href={`/chat/${conversationId}/`}
        $css={linkStyles}
        onClick={handleLinkClick}
      >
        {children}
      </StyledLink>

      {actions && <Box className="pinned-actions">{actions}</Box>}
    </Box>
  );
});
