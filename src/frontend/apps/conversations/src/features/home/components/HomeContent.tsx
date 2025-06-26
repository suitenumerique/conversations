import { Button } from '@openfun/cunningham-react';
import { Trans, useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Text } from '@/components';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { Footer } from '@/features/footer';
import { LeftPanel } from '@/features/left-panel';
import { useResponsiveStore } from '@/stores';

import SC5 from '../assets/SC5.png';
import GithubIcon from '../assets/github.svg';

import HomeBanner from './HomeBanner';
import { HomeBottom } from './HomeBottom';
import { HomeHeader, getHeaderHeight } from './HomeHeader';
import { HomeSection } from './HomeSection';

export function HomeContent() {
  const { t } = useTranslation();
  const { colorsTokens } = useCunninghamTheme();
  const { isMobile, isSmallMobile, isTablet } = useResponsiveStore();

  return (
    <Box as="main" className="--docs--home-content">
      <HomeHeader />
      {isSmallMobile && (
        <Box $css="& .--docs--left-panel-header{display: none;}">
          <LeftPanel />
        </Box>
      )}
      <Box
        $css={css`
          height: calc(100vh - ${getHeaderHeight(isSmallMobile)}px);
          overflow-y: auto;
        `}
      >
        <Box
          $align="center"
          $justify="center"
          $maxWidth="1120px"
          $padding={{ horizontal: isSmallMobile ? '1rem' : '3rem' }}
          $width="100%"
          $margin="auto"
        >
          <HomeBanner />
          <Box
            id="docs-app-info"
            $maxWidth="100%"
            $gap={isMobile ? '115px' : '230px'}
            $padding={{ bottom: '3rem' }}
          >
            <Box $gap={isMobile ? '115px' : '30px'}>
              <HomeSection
                isColumn={false}
                isSmallDevice={isTablet}
                illustration={SC5}
                title={t('Govs ❤️ Open Source.')}
                tag={t('Open Source')}
                textWidth="60%"
                $css={`min-height: calc(100vh - ${getHeaderHeight(isSmallMobile)}px);`}
                description={
                  <Box
                    $css={css`
                      & a {
                        color: ${colorsTokens['primary-600']};
                      }
                    `}
                  >
                    <Text as="p" $display="inline">
                      <Trans
                        t={t}
                        i18nKey="home-content-open-source-part1"
                        productName={productName}
                      >
                        {{ productName }} is built on top of{' '}
                        <a
                          href="https://www.django-rest-framework.org/"
                          target="_blank"
                        >
                          Django Rest Framework
                        </a>{' '}
                        and{' '}
                        <a href="https://nextjs.org/" target="_blank">
                          Next.js
                        </a>
                        . We also use{' '}
                        <a href="https://ai-sdk.dev/" target="_blank">
                          Vercel&lsquo;s AI SDK
                        </a>{' '}
                        and{' '}
                        <a
                          href="https://github.com/openai/openai-agents-python"
                          target="_blank"
                        >
                          OpenAI Agents SDK
                        </a>
                        .
                      </Trans>
                    </Text>
                    <Text as="p" $display="inline">
                      <Trans
                        t={t}
                        i18nKey="home-content-open-source-part2"
                        productName={productName}
                      >
                        You can easily self-host {{ productName }} (check our
                        installation{' '}
                        <a
                          href="https://github.com/suitenumerique/conversations/tree/main/docs"
                          target="_blank"
                        >
                          documentation
                        </a>
                        ).
                        <br />
                        {{ productName }} uses an innovation and business
                        friendly{' '}
                        <a
                          href="https://github.com/suitenumerique/conversations/blob/main/LICENSE"
                          target="_blank"
                        >
                          licence
                        </a>{' '}
                        (MIT).
                        <br />
                        Contributions are welcome (see our roadmap{' '}
                        <a
                          href="https://github.com/orgs/numerique-gouv/projects/13/views/11"
                          target="_blank"
                        >
                          here
                        </a>
                        ).
                      </Trans>
                    </Text>
                    <Box
                      $direction="row"
                      $gap="1rem"
                      $margin={{ top: 'small' }}
                    >
                      <Button
                        color="secondary"
                        icon={<GithubIcon />}
                        href="https://github.com/suitenumerique/conversations"
                        target="_blank"
                      >
                        Github
                      </Button>
                    </Box>
                  </Box>
                }
              />
            </Box>
            <HomeBottom />
          </Box>
        </Box>
        <Footer />
      </Box>
    </Box>
  );
}
