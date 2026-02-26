import { useRouter } from 'next/navigation';
import { PropsWithChildren, useState } from 'react';

import { Box } from '@/components';
import { useAuth } from '@/features/auth';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { useResponsiveStore } from '@/stores';

import { LeftPanelHeaderActions } from './LeftPanelHeaderActions';
import { LeftPanelSearchModal } from './LeftPanelSearchModal';

export const LeftPanelHeader = ({ children }: PropsWithChildren) => {
  const router = useRouter();
  const { authenticated } = useAuth();
  const { isDesktop } = useResponsiveStore();
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);

  const { setPanelOpen } = useChatPreferencesStore();

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
          />
          {children}
        </Box>
      )}
      <LeftPanelSearchModal
        isOpen={isSearchModalOpen}
        onClose={() => setIsSearchModalOpen(false)}
      />
    </>
  );
};
