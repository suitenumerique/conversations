import { type ReactNode, memo } from 'react';

import { Box, Text } from '@/components';

const WELCOME_PADDING = { all: 'base', bottom: 'md' } as const;
const WELCOME_MARGIN = {
  horizontal: 'base',
  bottom: 'md',
  top: '-105px',
} as const;
const WELCOME_TEXT_MARGIN = { all: '0' } as const;

interface WelcomeLayoutProps {
  title: string;
  icon?: ReactNode;
}

export const WelcomeLayout = memo(function WelcomeLayout({
  title,
  icon,
}: WelcomeLayoutProps) {
  return (
    <Box $padding={WELCOME_PADDING} $align="center" $margin={WELCOME_MARGIN}>
      <Box $direction="row" $align="center" $gap="10px">
        {icon}
        <Text as="h2" $size="xl" $weight="600" $margin={WELCOME_TEXT_MARGIN}>
          {title}
        </Text>
      </Box>
    </Box>
  );
});
