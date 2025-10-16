import { Button } from '@openfun/cunningham-react';
import { useRouter } from 'next/navigation';
import { useEffect as _useEffect, useState as _useState } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import NewChatIcon from '@/assets/icons/new-message-bold.svg';
import Logo from '@/assets/logo/logo-assistant.svg';
import { Box, StyledLink } from '@/components/';
import { productName } from '@/core';
import { useCunninghamTheme } from '@/cunningham';
import { ButtonLogin } from '@/features/auth';
import { useChatScroll } from '@/features/chat/hooks';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { Feedback } from '@/features/feedback/Feedback';
import { LanguagePicker } from '@/features/language';
import { useResponsiveStore } from '@/stores';

import { HEADER_HEIGHT } from '../conf';

import { ButtonToggleLeftPanel } from './ButtonToggleLeftPanel';
import { ButtonTogglePanel } from './ButtonTogglePanel';
import { LaGaufre } from './LaGaufre';

export const Header = () => {
  const { t } = useTranslation();
  const { spacingsTokens, colorsTokens } = useCunninghamTheme();
  const { isDesktop } = useResponsiveStore();
  const { setPanelOpen } = useChatPreferencesStore();
  const { isAtTop } = useChatScroll();
  const router = useRouter();

  return (
    <Box
      as="header"
      $css={css`
        position: sticky;
        top: 0;
        right: 0;
        z-index: 1000;
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
        height: ${isDesktop ? HEADER_HEIGHT : '52'}px;
        padding: 0 ${spacingsTokens['base']};
        background-color: ${colorsTokens['greyscale-000']};
        border-bottom: ${isAtTop
          ? `1px solid transparent`
          : `1px solid ${colorsTokens['greyscale-100']}`};
        transition: border-bottom 0.2s ease;
      `}
      className="--docs--header"
    >
      {!isDesktop && <ButtonTogglePanel />}
      <Box
        $align="center"
        $gap={spacingsTokens['xs']}
        $direction="row"
        $position="relative"
        $height="fit-content"
      >
        {isDesktop && <ButtonToggleLeftPanel />}
        <StyledLink href="/">
          <Logo
            aria-label={t('{{productName}} Logo', { productName })}
            width={139}
            color={colorsTokens['primary-text']}
          />
        </StyledLink>
        <Box className="c__button--feedback">{isDesktop && <Feedback />}</Box>
      </Box>
      {!isDesktop ? (
        <Box $direction="row" $gap={spacingsTokens['sm']}>
          <Button
            size="medium"
            onClick={() => {
              router.push('/');
              setPanelOpen(false);
            }}
            className="mobile-no-focus"
            aria-label={t('New chat')}
            color="primary-text"
            icon={<NewChatIcon />}
          />
        </Box>
      ) : (
        <Box
          $align="center"
          $gap={spacingsTokens['sm']}
          $direction="row"
          $css={css`
            height: '52px';
          `}
        >
          <ButtonLogin />
          <LanguagePicker />
          <LaGaufre />
        </Box>
      )}
    </Box>
  );
};
