import { useRouter } from 'next/router';
import { PropsWithChildren, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import Logo from '@/assets/logo/logo-assistant.svg';
import { Button } from '@gouvfr-lasuite/cunningham-react';
import { Box, Icon, StyledLink } from '@/components';
import { useAuth } from '@/features/auth';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { useOwnModal } from '@/features/left-panel/hooks/useModalHook';
import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';
import { useResponsiveStore } from '@/stores';

import { ModalProjectForm } from '../projects/ModalProjectForm';

import { LeftPanelHeaderActions } from './LeftPanelHeaderActions';
import { LeftPanelSearchModal } from './LeftPanelSearchModal';

export const LeftPanelHeader = ({ children }: PropsWithChildren) => {
  const router = useRouter();
  const { t } = useTranslation();
  const { authenticated } = useAuth();
  const { isDesktop } = useResponsiveStore();
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);
  const createProjectModal = useOwnModal();
  const setProjectId = usePendingChatStore((s) => s.setProjectId);

  const { setPanelOpen } = useChatPreferencesStore();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsSearchModalOpen((open) => !open);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const goToHome = () => {
    setProjectId(null);
    void router.push('/');
    if (!isDesktop) {
      setPanelOpen(false);
    }
  };

  return (
    <>
      <Box
        $width="100%"
        $padding={{ horizontal: 'sm', top: 'sm' }}
        $direction="row"
        $justify={isDesktop ? 'flex-start' : 'space-between'}
        $align="center"
      >
        <StyledLink href="/">
          <Logo
            aria-label="Assistant Logo"
            width={139}
            color="var(--c--globals--colors--logo-1-light)"
          />
        </StyledLink>
        {!isDesktop && (
          <Button
            aria-label={t('Close the menu')}
            onClick={() => setPanelOpen(false)}
            color="neutral"
            variant="tertiary"
            icon={
              <Icon iconName="close" $theme="neutral" $variation="neutral" />
            }
          />
        )}
      </Box>
      {authenticated && (
        <Box $width="100%" className="--docs--left-panel-header">
          <LeftPanelHeaderActions
            onNewChat={goToHome}
            onSearch={() => {
              if (!isDesktop) {
                setPanelOpen(false);
              }
              setIsSearchModalOpen(true);
            }}
            onCreateProject={createProjectModal.open}
          />
          {children}
        </Box>
      )}
      {/* Mount only when needed to avoid running hooks while closed */}
      {authenticated && isSearchModalOpen && (
        <LeftPanelSearchModal onClose={() => setIsSearchModalOpen(false)} />
      )}
      {authenticated && createProjectModal.isOpen && (
        <ModalProjectForm onClose={createProjectModal.close} />
      )}
    </>
  );
};
