import { useRouter } from 'next/navigation';
import { PropsWithChildren, useEffect, useState } from 'react';

import { Box } from '@/components';
import { useAuth } from '@/features/auth';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { useOwnModal } from '@/features/left-panel/hooks/useModalHook';
import { useResponsiveStore } from '@/stores';

import { LeftPanelHeaderActions } from './LeftPanelHeaderActions';
import { LeftPanelSearchModal } from './LeftPanelSearchModal';
import { ModalCreateProject } from './ModalCreateProject';

export const LeftPanelHeader = ({ children }: PropsWithChildren) => {
  const router = useRouter();
  const { authenticated } = useAuth();
  const { isDesktop } = useResponsiveStore();
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);
  const createProjectModal = useOwnModal();

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
    router.push('/');
    if (!isDesktop) {
      setPanelOpen(false);
    }
  };

  return (
    <>
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
        <ModalCreateProject onClose={createProjectModal.close} />
      )}
    </>
  );
};
