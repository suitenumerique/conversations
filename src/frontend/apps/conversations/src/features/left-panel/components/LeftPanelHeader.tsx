import { Button } from '@openfun/cunningham-react';
import { t } from 'i18next';
import { useRouter } from 'next/navigation';
import { PropsWithChildren } from 'react';

import NewChatIcon from '@/assets/icons/new-message-bold.svg';
import { Box, SeparatedSection } from '@/components';
import { useAuth } from '@/features/auth';
import { SettingsButton } from '@/features/settings';
import { useResponsiveStore } from '@/stores';

import { useLeftPanelStore } from '../stores';

export const LeftPanelHeader = ({ children }: PropsWithChildren) => {
  const router = useRouter();
  const { authenticated } = useAuth();
  const { isDesktop } = useResponsiveStore();

  const { togglePanel } = useLeftPanelStore();

  const goToHome = () => {
    router.push('/');
    if (!isDesktop) {
      togglePanel(false);
    }
  };

  return (
    <>
      {authenticated && (
        <Box $width="100%" className="--docs--left-panel-header">
          <SeparatedSection>
            <Box
              $padding={{ horizontal: 'sm' }}
              $width="100%"
              $direction="row"
              $justify="space-between"
              $align="center"
            >
              <Box $direction="row" $gap="2px">
                <Button
                  color="primary"
                  icon={<NewChatIcon />}
                  onClick={goToHome}
                >
                  {t('New chat')}
                </Button>
              </Box>
              <SettingsButton />
            </Box>
          </SeparatedSection>
          {children}
        </Box>
      )}
    </>
  );
};
