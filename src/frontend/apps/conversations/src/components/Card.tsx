import { PropsWithChildren } from 'react';
import { css } from 'styled-components';

import { useCunninghamTheme } from '@/cunningham';

import { Box, BoxType } from '.';

export const Card = ({
  children,
  $css,
  ...props
}: PropsWithChildren<BoxType>) => {
  const { colorsTokens } = useCunninghamTheme();

  return (
    <Box
      className={`--docs--card ${props.className || ''}`}
      $background="white"
      $radius="4px"
      {...props}
    >
      {children}
    </Box>
  );
};
