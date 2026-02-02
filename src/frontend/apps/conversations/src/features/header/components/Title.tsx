import { Box, Text } from '@/components/';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';

export const Title = () => {
  const { spacingsTokens, colorsTokens } = useCunninghamTheme();

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
        $color={colorsTokens['logo-1-light']}
        $zIndex={1}
        $size="1.375rem"
      >
        {productName}
      </Text>
      {/*      {!!badgeText && (
        <Text
          $padding={{
            horizontal: '6px',
            vertical: '4px',
          }}
          $size="11px"
          $theme="primaryc"
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
      )}*/}
    </Box>
  );
};
