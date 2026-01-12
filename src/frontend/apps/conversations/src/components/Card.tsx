import { PropsWithChildren } from 'react';

import { Box, BoxType } from '.';

export const Card = ({ children, ...props }: PropsWithChildren<BoxType>) => {
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
