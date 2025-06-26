import { Button } from '@openfun/cunningham-react';
import { t } from 'i18next';
import { useRouter } from 'next/navigation';
import { PropsWithChildren, useCallback, useState } from 'react';

import { Box, Icon, SeparatedSection } from '@/components';
import { useAuth } from '@/features/auth';
import { ConversationSearchModal } from '@/features/chat-search';
import { useCmdK } from '@/hook/useCmdK';

import { useLeftPanelStore } from '../stores';

export const LeftPanelHeader = ({ children }: PropsWithChildren) => {
  const router = useRouter();
  const { authenticated } = useAuth();
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);

  const openSearchModal = useCallback(() => {
    const isEditorToolbarOpen =
      document.getElementsByClassName('bn-formatting-toolbar').length > 0;
    if (isEditorToolbarOpen) {
      return;
    }

    setIsSearchModalOpen(true);
  }, []);

  const closeSearchModal = useCallback(() => {
    setIsSearchModalOpen(false);
  }, []);

  useCmdK(openSearchModal);
  const { togglePanel } = useLeftPanelStore();

  const goToHome = () => {
    router.push('/');
    togglePanel();
  };

  return (
    <>
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
                onClick={goToHome}
                size="medium"
                color="tertiary-text"
                icon={
                  <Icon $variation="800" $theme="primary" iconName="house" />
                }
              />
              {authenticated && (
                <Button
                  onClick={openSearchModal}
                  size="medium"
                  color="tertiary-text"
                  icon={
                    <Icon $variation="800" $theme="primary" iconName="search" />
                  }
                />
              )}
            </Box>
            {authenticated && (
              <Button onClick={goToHome}>{t('New conversation')}</Button>
            )}
          </Box>
        </SeparatedSection>
        {children}
      </Box>
      {isSearchModalOpen && (
        <ConversationSearchModal
          onClose={closeSearchModal}
          isOpen={isSearchModalOpen}
        />
      )}
    </>
  );
};
