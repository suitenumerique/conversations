import { Modal, ModalSize } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Box, Text, ToggleSwitch, useToast } from '@/components';
import { useUserUpdate } from '@/core/api/useUserUpdate';
import { useCunninghamTheme } from '@/cunningham';
import { useAuthQuery } from '@/features/auth/api';

interface SettingsModalProps {
  onClose: () => void;
  isOpen: boolean;
}

const STATUS_I18N_KEYS: Record<
  'allow_conversation_analytics' | 'allow_smart_web_search',
  { enabled: string; disabled: string }
> = {
  allow_conversation_analytics: {
    enabled: 'Conversation analysis enabled',
    disabled: 'Conversation analysis disabled',
  },
  allow_smart_web_search: {
    enabled: 'Automatic web search enabled',
    disabled: 'Automatic web search disabled',
  },
};

export const SettingsModal = ({ onClose, isOpen }: SettingsModalProps) => {
  const { t } = useTranslation();
  const { data: user } = useAuthQuery();
  const { mutateAsync: updateUser, isPending } = useUserUpdate();
  const { showToast } = useToast();
  const { isDarkMode, toggleDarkMode } = useCunninghamTheme();

  const handleToggleChange = async (
    field: 'allow_conversation_analytics' | 'allow_smart_web_search',
  ) => {
    if (!user) {
      return;
    }

    try {
      const updatedValue = !user[field];
      await updateUser({
        id: user.id,
        [field]: updatedValue,
      });

      const toastMessage = updatedValue
        ? t(STATUS_I18N_KEYS[field].disabled)
        : t(STATUS_I18N_KEYS[field].enabled);
      showToast('success', toastMessage, 'check_circle', 3000);
    } catch (error) {
      console.error(`Error updating user settings for ${field}:`, error);
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
        <Box $justify="space-between">
          {/* Intro */}
          <Box $gap="2xs">
            <Text
              $size="xs"
              $weight="400"
              $theme="greyscale"
              $variation="600"
              $padding={{ top: 'sm', bottom: 'sm' }}
            >
              {t(
                'The Assistant is a sovereign AI for public servants. It helps with daily tasks (rephrasing, summarising, translating, information search). Your data stays in France on secure, state-compliant infrastructure and is never used for commercial purposes.',
              )}
            </Text>
          </Box>

          {/* Conversation Analytics  */}
          <Box $gap="2xs">
            <Text
              $size="md"
              $weight="500"
              $theme="greyscale"
              $variation="850"
              $padding={{ top: 'xs', bottom: 'xs' }}
            >
              {t('Allow conversation analysis')}
            </Text>

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
                  $padding={{ top: 'sm', bottom: 'sm' }}
                >
                  {t(
                    'If enabled, this allows us to analyse your exchanges to improve the Assistant. If disabled, all conversations remain confidential and are not used in any way. ',
                  )}
                  <a
                    style={{
                      display: 'inline-block',
                      color:
                        'var(--c--contextuals--content--semantic--neutral--primary)',
                    }}
                    target="_blank"
                    rel="noopener noreferrer"
                    href="https://docs.numerique.gouv.fr/docs/53d1dfb9-481d-4a68-b75c-7208c03d4dec/"
                  >
                    {t('Learn more about data usage.')}
                  </a>
                </Text>
              </Box>
              <ToggleSwitch
                checked={user?.allow_conversation_analytics ?? false}
                onChange={() =>
                  void handleToggleChange('allow_conversation_analytics')
                }
                disabled={isPending}
                aria-label={t('Allow conversation analysis')}
              />
            </Box>
          </Box>

          {/* Smart Web Search (title + description + Dark Mode spacing) */}
          <Box $gap="2xs">
            <Text
              $size="md"
              $weight="500"
              $theme="greyscale"
              $variation="850"
              $padding={{ top: 'xs', bottom: 'xs' }}
            >
              {t('Automatic web search')}
            </Text>
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
                  $padding={{ top: 'sm', bottom: 'sm' }}
                >
                  {t(
                    "The Assistant automatically decides when to perform a web search to enrich responses. If disabled, the Assistant will not use the web unless you click the 'Search the web' button.",
                  )}
                </Text>
              </Box>
              <ToggleSwitch
                checked={user?.allow_smart_web_search ?? false}
                onChange={() =>
                  void handleToggleChange('allow_smart_web_search')
                }
                disabled={isPending}
                aria-label={t('Automatic web search')}
              />
            </Box>
          </Box>

          {/* Dark Mode (exact copy of your box) */}
          <Box
            $display="block"
            $justify="space-between"
            $align="flex-end"
            $gap="2xs"
            $padding={{ top: 'md' }}
            $css="min-width: 100%;"
          >
            <Box
              $direction="row"
              $justify="space-between"
              $css="min-width: 70%;"
            >
              <Box $css="min-width: 70%;">
                <Text
                  $size="md"
                  $weight="500"
                  $theme="greyscale"
                  $variation="850"
                >
                  {t('Dark mode')}
                </Text>
              </Box>
              <ToggleSwitch
                checked={isDarkMode}
                onChange={() => toggleDarkMode()}
                aria-label={t('Dark mode')}
              />
            </Box>
          </Box>
        </Box>
      </Box>
    </Modal>
  );
};
