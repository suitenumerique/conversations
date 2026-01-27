import { Modal, ModalSize } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Box, StyledLink, Text, ToggleSwitch, useToast } from '@/components';
import { HorizontalSeparator } from '@/components/separators/HorizontalSeparator';
import { useUserUpdate } from '@/core/api/useUserUpdate';
import { useCunninghamTheme } from '@/cunningham';
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
  const { isDarkMode, toggleDarkMode } = useCunninghamTheme();

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
      title={t('Assistant settings')}
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

            <Box $gap="2xs" $padding={{ top: 'md' }}>
              <Text
                $size="md"
                $weight="500"
                $theme="greyscale"
                $variation="850"
              >
                {t('Dark mode')}
              </Text>
              <Box
                $direction="row"
                $justify="space-between"
                $align="flex-start"
              >
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
                      'Enable dark mode to reduce eye strain in low-light environments.',
                    )}
                  </Text>
                </Box>
                <ToggleSwitch
                  checked={isDarkMode}
                  onChange={() => toggleDarkMode()}
                  aria-label={t('Dark mode')}
                />
              </Box>
            </Box>

            <HorizontalSeparator />

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
            <ToggleSwitch
              checked={user?.allow_conversation_analytics ?? false}
              onChange={() => void handleToggleChange()}
              disabled={isPending}
              aria-label={t('Allow conversation analysis')}
            />
          </Box>
        </Box>
      </Box>
    </Modal>
  );
};
