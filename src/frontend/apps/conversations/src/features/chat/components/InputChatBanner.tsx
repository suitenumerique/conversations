import { ReactNode } from 'react';

import { Box, Text } from '@/components';

// Tab-like strip peeking above the input card: rounded top corners, extra
// bottom padding and a negative margin so the card overlaps its bottom edge.
// The variant's content color is set on the root so the icon (currentColor)
// inherits it, and forced onto the action button so it matches too.
const bannerCss = (contentColor: string) => `
  padding: 8px 16px 20px;
  margin-bottom: -12px;
  border-top-left-radius: 12px;
  border-top-right-radius: 12px;
  text-align: left;
  color: ${contentColor};

  & .c__button {
    color: ${contentColor};
  }
`;

const VARIANT_COLORS = {
  error: {
    background: 'var(--c--contextuals--background--semantic--error--tertiary)',
    content: 'var(--c--contextuals--content--semantic--error--primary)',
  },
  neutral: {
    background:
      'var(--c--contextuals--background--semantic--neutral--tertiary)',
    content: 'var(--c--contextuals--content--semantic--neutral--primary)',
  },
  warning: {
    background:
      'var(--c--contextuals--background--semantic--warning--tertiary)',
    content: 'var(--c--contextuals--content--semantic--warning--primary)',
  },
} as const;

interface InputChatBannerProps {
  icon: ReactNode;
  text: string;
  action?: ReactNode;
  variant?: keyof typeof VARIANT_COLORS;
}

export const InputChatBanner = ({
  icon,
  text,
  action,
  variant = 'warning',
}: InputChatBannerProps) => {
  const colors = VARIANT_COLORS[variant];

  return (
    <Box
      role="status"
      $align="center"
      $direction="row"
      $justify="space-between"
      $gap="8px"
      $background={colors.background}
      $css={bannerCss(colors.content)}
    >
      <Box $align="center" $direction="row" $gap="8px" $color={colors.content}>
        {icon}
        <Text $weight="700" $size="sm" $color={colors.content}>
          {text}
        </Text>
      </Box>
      {action}
    </Box>
  );
};
