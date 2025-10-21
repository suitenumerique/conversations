import { Modal, ModalSize } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, StyledLink, Text, useToast } from '@/components';
import { useUserUpdate } from '@/core/api/useUserUpdate';
import { useAuthQuery } from '@/features/auth/api';

interface SettingsModalProps {
  onClose: () => void;
  isOpen: boolean;
}

export const SettingsModal = ({ onClose, isOpen }: SettingsModalProps) => {
  const { t } = useTranslation();
  const { data: user } = useAuthQuery();
  const { mutateAsync: updateUser, isPending } = useUserUpdate();
  const { showToast } = useToast();

  const handleToggleChange = async () => {
    if (!user) {
      return;
    }

    try {
      await updateUser({
        id: user.id,
        allow_conversation_analytics: !user.allow_conversation_analytics,
      });

      // Toast de succès
      showToast(
        'success',
        user.allow_conversation_analytics
          ? t('Conversation analysis disabled')
          : t('Conversation analysis enabled'),
        'check_circle',
        3000,
      );
    } catch (error) {
      console.error('Error updating user settings:', error);

      // Toast d'erreur
      showToast('error', t('Failed to update settings'), 'error', 3000);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      closeOnClickOutside
      onClose={onClose}
      size={ModalSize.MEDIUM}
      title={
        <Text
          $size="h6"
          as="h6"
          $margin={{ all: '0' }}
          $align="flex-start"
          $theme="greyscale"
          $variation="850"
        >
          {t('Assistant settings')}
        </Text>
      }
    >
      <Box aria-label={t('Assistant settings')}>
        <Box $align="center" $justify="space-between">
          <Box $gap="2xs">
            <Text
              $size="xs"
              $weight="400"
              $theme="greyscale"
              $variation="600"
              $padding={{ top: 'sm', bottom: 'sm' }}
            >
              {t(
                'The Assistant is a sovereign conversational AI designed for public servants. It helps you save time on daily tasks like rephrasing, summarising, translating, or searching information. Your data never leaves France and is stored on secure, state-compliant infrastructures. It is never used for commercial purposes.',
              )}
            </Text>
            <Text
              $size="md"
              $weight="500"
              $theme="greyscale"
              $variation="850"
              $padding={{ top: 'xs' }}
            >
              {t('Allow conversation analysis')}
            </Text>
          </Box>
          <Box $direction="row" $justify="space-between" $align="flex-start">
            <Box $css="max-width: 70%;">
              <Text
                $css={`
                  display: inline-block;
                `}
                $size="xs"
                $theme="greyscale"
                $variation="600"
                $weight="400"
              >
                {t(
                  'If enabled, this allows us to analyse your exchanges to improve the Assistant. If disabled, all conversations remain confidential and are not used in any way. ',
                )}
                <StyledLink
                  $css={`
                    display: inline-block;
                  `}
                  target="_blank"
                  href="https://docs.numerique.gouv.fr/docs/53d1dfb9-481d-4a68-b75c-7208c03d4dec/"
                >
                  <Text
                    $css={`
                    text-decoration: underline !important;
                  `}
                    $size="xs"
                    $theme="greyscale"
                    $variation="600"
                    $weight="400"
                  >
                    {t('Learn more about data usage.')}
                  </Text>
                </StyledLink>
              </Text>
            </Box>
            <Box $css="padding-top: 2px;">
              <Box
                $css={`
                    position: relative;
                    width: 44px;
                    height: 24px;
                    background-color: ${user?.allow_conversation_analytics ? 'var(--c--theme--colors--primary-500)' : 'var(--c--theme--colors--greyscale-300)'};
                    border-radius: 12px;
                    cursor: ${isPending ? 'not-allowed' : 'pointer'};
                    transition: all 0.2s ease;
                    opacity: ${isPending ? 0.6 : 1};
                  `}
                onClick={
                  isPending ? undefined : () => void handleToggleChange()
                }
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    if (!isPending) {
                      void handleToggleChange();
                    }
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <Box
                  $css={`
                    position: absolute;
                    top: 2px;
                    left: ${user?.allow_conversation_analytics ? '22px' : '2px'};
                    width: 20px;
                    height: 20px;
                    background-color: white;
                    border-radius: 50%;
                    transition: left 0.2s ease;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                  `}
                >
                  <Icon
                    iconName={user?.allow_conversation_analytics ? 'check' : ''}
                    $size="12px"
                    $theme="primary"
                    $variation="600"
                  />
                </Box>
              </Box>
            </Box>
          </Box>
        </Box>
      </Box>
    </Modal>
  );
};
