import { Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Box,
  DropdownMenu,
  type DropdownMenuOption,
  StyledLink,
  Text,
  ToggleSwitch,
} from '@/components';
import { useUserUpdate } from '@/core/api/useUserUpdate';
import { useAuthQuery } from '@/features/auth/api';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';
import { useResponsiveStore } from '@/stores/useResponsiveStore';

interface SettingsModalProps {
  onClose: () => void;
  isOpen: boolean;
}

export const SettingsModal = ({ onClose, isOpen }: SettingsModalProps) => {
  const { t } = useTranslation();
  const { isMobile } = useResponsiveStore();
  const { data: user } = useAuthQuery();
  const { mutateAsync: updateUser, isPending } = useUserUpdate();
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

  const generalSettings = () => {
    return (
      <>
        <Box
          $display="block"
          $justify="space-between"
          $align="flex-end"
          $css="min-width: 100%;"
        >
          <Box
            $direction={isMobile ? 'column' : 'row'}
            $justify="space-between"
            $align={isMobile ? 'flex-start' : 'flex-end'}
          >
            <Box $css="min-width: 70%;">
              <Text $size="md" $weight="500" $theme="neutral" $variation="850">
                {t('Appearance')}
              </Text>

              <Text $variation="400" $theme="neutral">
                {t('Customize how the Assistant looks on your device.')}
              </Text>
            </Box>
            <DropdownMenu
              buttonColor="brand"
              label={t('Appearance theme')}
              options={colorModeOptions}
              showArrow
            >
              {selectedColorModeLabel}
            </DropdownMenu>
          </Box>
        </Box>
      </>
    );
  };

  const capabilitiesSettings = () => (
    <>
      <Box $gap="2xs">
        <Text
          $size="sm"
          $weight="400"
          $theme="greyscale"
          $variation="600"
          $padding={{ bottom: 'base' }}
        >
          {t(
            'The Assistant is a sovereign AI for public servants. It helps with daily tasks (rephrasing, summarising, translating, information search). Your data stays in France on secure, state-compliant infrastructure and is never used for commercial purposes.',
          )}
        </Text>

        <Box>
          <Text $size="md" $weight="500" $theme="greyscale" $variation="850">
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
                $padding={{ bottom: 'sm' }}
              >
                {t(
                  'The assistant automatically decides when to search the web. If you turn this off, it won’t go online unless you click “Research on the web.”',
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

        <Box $gap="2xs">
          <Text
            $size="md"
            $weight="500"
            $theme="greyscale"
            $variation="850"
            $padding={{ top: 'xs' }}
          >
            {t('Allow conversation analysis')}
          </Text>
          <Box $direction="row" $justify="space-between" $align="center">
            <Box $css="max-width: 70%;">
              <Text
                $css={`
                  display: inline-block;
                `}
                $size="xs"
                $theme="greyscale"
                $variation="600"
                $weight="400"
                $padding={{ bottom: 'sm' }}
              >
                {t(
                  'If enabled, this allows us to analyse your exchanges to improve the Assistant. If disabled, all conversations remain confidential and are not used in any way. ',
                )}
                <StyledLink
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={t(
                    'Learn more about data usage (open in new tab)',
                  )}
                  href="https://docs.numerique.gouv.fr/docs/53d1dfb9-481d-4a68-b75c-7208c03d4dec/"
                  $css={`
                    display: inline;
                    color: var(--c--contextuals--content--semantic--neutral--primary);
                    text-decoration: underline;
                    text-underline-offset: 2px;
                    &:focus-visible {
                      outline: 2px solid var(--c--globals--colors--brand-400);
                      outline-offset: 2px;
                      border-radius: 4px;
                    }
                  `}
                >
                  {t('Learn more about data usage.')}
                </StyledLink>
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
      </Box>
    </>
  );

  const settingsTabs = [
    {
      id: 'general',
      label: t('General'),
      title: t('General'),
      content: generalSettings(),
    },
    {
      id: 'capabilities',
      label: t('Capabilities'),
      title: t('Capabilities'),
      content: capabilitiesSettings(),
    },
  ];

  const tabModalProps = {
    isOpen,
    closeOnClickOutside: true,
    onClose,
    size: ModalSize.LARGE,
    tabs: settingsTabs,
    sidebarTitle: t('Settings'),
    variant: 'tab' as const,
  } as unknown as React.ComponentProps<typeof Modal>;

  return <Modal {...tabModalProps} />;
};
