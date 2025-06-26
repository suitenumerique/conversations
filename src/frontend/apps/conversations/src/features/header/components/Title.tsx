import { css } from 'styled-components';

import { Box, Text } from '@/components/';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';

export const Title = () => {
  const { spacingsTokens, colorsTokens, componentTokens } =
    useCunninghamTheme();
  const isAlpha = componentTokens['alpha'];
  const isBeta = componentTokens['beta'];

  const badgeText = isAlpha ? 'ALPHA' : isBeta ? 'BETA' : '';

  return (
    <Box
      $direction="row"
      $align="center"
      $gap={spacingsTokens['2xs']}
      className="--docs--title"
    >
      <Text
        $margin="none"
        as="h2"
        $color={colorsTokens['primary-text']}
        $zIndex={1}
        $size="1.375rem"
      >
        {productName}
      </Text>
      {!!badgeText && (
        <Text
          $padding={{
            horizontal: '6px',
            vertical: '4px',
          }}
          $size="11px"
          $theme="primary"
          $variation="500"
          $weight="bold"
          $radius="12px"
          $css={css`
            line-height: 9px;
          `}
          $width="40px"
          $height="16px"
          $background="#ECECFF"
          $color="#5958D3"
        >
          {badgeText}
        </Text>
      )}
    </Box>
  );
};
