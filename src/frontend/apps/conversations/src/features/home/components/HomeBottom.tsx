import { useTranslation } from 'react-i18next';

import IconAssistant from '@/assets/logo/assistant.svg';
import { Box, Text } from '@/components';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { ProConnectButton } from '@/features/auth';
import { Title } from '@/features/header';
import { useResponsiveStore } from '@/stores';

export function HomeBottom() {
  const { componentTokens } = useCunninghamTheme();
  const withProConnect = componentTokens['home-proconnect'];

  if (!withProConnect) {
    return null;
  }

  return <HomeProConnect />;
}

function HomeProConnect() {
  const { t } = useTranslation();
  const { spacingsTokens, colorsTokens } = useCunninghamTheme();
  const { isMobile } = useResponsiveStore();
  const parentGap = '230px';

  return (
    <Box
      $justify="center"
      $height={!isMobile ? `calc(100vh - ${parentGap})` : 'auto'}
      className="--docs--home-proconnect"
    >
      <Box
        $gap={spacingsTokens['md']}
        $direction="column"
        $align="center"
        $margin={{ top: isMobile ? 'none' : `-${parentGap}` }}
      >
        <Box
          $align="center"
          $gap={spacingsTokens['3xs']}
          $direction="row"
          $position="relative"
          $height="fit-content"
          $css="zoom: 1.9;"
        >
          <IconAssistant
            aria-label={t('{{productName}} Logo', { productName })}
            width={34}
            color={colorsTokens['primary-text']}
          />
          <Title />
        </Box>
        <Text $size="md" $variation="1000" $textAlign="center">
          {t('Assistant is already available, log in to use it now.')}
        </Text>
        <ProConnectButton />
      </Box>
    </Box>
  );
}
