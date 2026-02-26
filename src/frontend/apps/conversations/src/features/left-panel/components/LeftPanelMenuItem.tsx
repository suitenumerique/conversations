import { ReactNode } from 'react';
import { css } from 'styled-components';

import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';

const menuItemCss = css`
  cursor: pointer;
  border-radius: var(--c--globals--spacings--xs);
  border: none;
  background: transparent;
  width: 100%;
  text-align: left;
  transition: background-color 0.2s ease;

  &:hover,
  &:focus-visible {
    background-color: var(
      --c--contextuals--background--semantic--overlay--primary
    );
  }
`;

const labelCss = css`
  color: var(--c--contextuals--content--semantic--neutral--primary);
  text-overflow: ellipsis;
  font-family: var(--c--globals--font--families--base);
  font-size: 0.875rem;
  font-weight: 500;
  overflow: hidden;
  white-space: nowrap;
`;

type LeftPanelMenuItemProps = {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  'aria-label': string;
};

export const LeftPanelMenuItem = ({
  icon,
  label,
  onClick,
  'aria-label': ariaLabel,
}: LeftPanelMenuItemProps) => {
  const { spacingsTokens } = useCunninghamTheme();

  return (
    <Box
      as="button"
      type="button"
      $direction="row"
      $align="center"
      $gap={spacingsTokens.xs}
      $padding={{ horizontal: 'xs', vertical: 'xs' }}
      $css={menuItemCss}
      onClick={onClick}
      aria-label={ariaLabel}
    >
      <Box $shrink={0} $display="flex" $align="center">
        {icon}
      </Box>
      <Text $css={labelCss} $shrink={1} $minWidth={0}>
        {label}
      </Text>
    </Box>
  );
};
