import { Button, Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react';
import { CSSProperties, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Box,
  DropdownMenu,
  DropdownMenuOption,
  SidebarModalLayout,
  Text,
  ToggleSwitch,
} from '@/components';
import { useUserUpdate } from '@/core/api/useUserUpdate';
import { useAuthQuery } from '@/features/auth/api';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

interface SettingsModalProps {
  onClose: () => void;
  isOpen: boolean;
}

const settingsModalTitle: CSSProperties = {
  margin: 0,
  fontSize: 'var(--c--globals--font--sizes--lg)',
  fontWeight: 700,
  color: 'var(--c--contextuals--content--semantic--neutral--primary)',
};

type SettingsSection = 'general' | 'capabilities' | 'connectors';

export const SettingsModal = ({ onClose, isOpen }: SettingsModalProps) => {
  const { t } = useTranslation();
  const { data: user } = useAuthQuery();
  const { mutateAsync: updateUser, isPending } = useUserUpdate();
  const [activeSection, setActiveSection] = useState<SettingsSection>('general');
  const themeModePreference = useChatPreferencesStore(
    (state) => state.themeModePreference,
  );
  const setThemeModePreference = useChatPreferencesStore(
    (state) => state.setThemeModePreference,
  );

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
    } catch (error) {
      console.error(`Error updating user settings for ${field}:`, error);
    }
  };

  const sectionItems: { id: SettingsSection; label: string }[] = [
    { id: 'general', label: t('General') },
    { id: 'capabilities', label: t('Capabilities') },
    // { id: 'connectors', label: t('Connectors') },
  ];

  const colorModeOptions: DropdownMenuOption[] = useMemo(
    () => [
      {
        label: t('Use system settings'),
        isSelected: themeModePreference === 'system',
        callback: () => setThemeModePreference('system'),
      },
      {
        label: t('Light'),
        isSelected: themeModePreference === 'light',
        callback: () => setThemeModePreference('light'),
      },
      {
        label: t('Dark'),
        isSelected: themeModePreference === 'dark',
        callback: () => setThemeModePreference('dark'),
      },
    ],
    [setThemeModePreference, t, themeModePreference],
  );

  const selectedColorModeLabel = useMemo(() => {
    if (themeModePreference === 'dark') {
      return t('Dark');
    }
    if (themeModePreference === 'light') {
      return t('Light');
    }
    return t('Use system settings');
  }, [t, themeModePreference]);

  return (
    <Modal
      isOpen={isOpen}
      closeOnClickOutside={false}
      onClose={onClose}
      size={ModalSize.LARGE}
    >
      <SidebarModalLayout
        aria-label={t('Assistant settings')}
        title={t('Settings')}
        items={sectionItems}
        activeItemId={activeSection}
        onItemSelect={(id) => setActiveSection(id as SettingsSection)}
      >
        {activeSection === 'general' && (
          <>
            <Box $gap="2xs">
              <h3 style={settingsModalTitle}>
                {t('General')}
              </h3>

              <Text
                $size="md"
                $weight="500"
                $theme="neutral"
                $variation="850"
                $padding={{ top: 'md'}}
              >
                {t('Appearance')}
              </Text>
            </Box>

            <Box
              $display="block"
              $justify="space-between"
              $align="flex-end"
              $gap="2xs"
              $css="min-width: 100%;"
            >
              <Box
                $direction="row"
                $justify="space-between"
              >
                <Box $css="min-width: 70%;">
                  <Text
                    $variation="400"
                    $theme="neutral"
                  >
                    {t('Customize how the Assistant looks on your device.')}
                  </Text>
                </Box>
                <DropdownMenu options={colorModeOptions} showArrow>
                  <Button
                    size="small"
                    variant="tertiary"
                  >
                    {selectedColorModeLabel}
                  </Button>
                </DropdownMenu>

              </Box>
            </Box>
          </>
        )}

        {activeSection === 'capabilities' && (
          <>
            <Box $gap="2xs">
              <h3 style={settingsModalTitle}>
                {t('Capabilities')}
              </h3>

            <Text
                $size="sm"
                $weight="400"
                $theme="greyscale"
                $variation="600"
                $padding={{ top: 'sm', bottom: 'sm' }}
              >
                {t(
                  'The Assistant is a sovereign AI for public servants. It helps with daily tasks (rephrasing, summarising, translating, information search). Your data stays in France on secure, state-compliant infrastructure and is never used for commercial purposes.'
                )}
              </Text>

                          <Box $gap="2xs">
              <Text
                $size="md"
                $weight="500"
                $theme="greyscale"
                $variation="850"
                $padding={{ top: 'xs', bottom: 'xs' }}
              >
                {t('Smart web search')}
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
                      "The assistant automatically decides when to search the web. If you turn this off, it won’t go online unless you click “Research on the web.”",
                    )}
                  </Text>
                </Box>
                <ToggleSwitch
                  checked={user?.allow_smart_web_search ?? false}
                  onChange={() => void handleToggleChange('allow_smart_web_search')}
                  disabled={isPending}
                  aria-label={t('Automatic web search')}
                />
              </Box>
            </Box>


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
          </>
        )}

        {activeSection === 'connectors' && (
          <Box $gap="2xs">
            <Text
              $size="md"
              $weight="500"
              $theme="greyscale"
              $variation="850"
              $padding={{ top: 'xs', bottom: 'xs' }}
            >
              {t('Connectors')}
            </Text>
            <Text
              $size="xs"
              $weight="400"
              $theme="greyscale"
              $variation="600"
              $padding={{ top: 'sm', bottom: 'sm' }}
            >
              {t('No connector is available yet.')}
            </Text>
          </Box>
        )}
      </SidebarModalLayout>
    </Modal>
  );
};
