import { Button } from '@gouvfr-lasuite/cunningham-react';
import { DropdownMenu, type DropdownMenuItem } from '@gouvfr-lasuite/ui-kit';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import QuestionMarkCircleIcon from '@/assets/icons/uikit-custom/question-mark-circle.svg';
import { Icon } from '@/components';
import { useConfig } from '@/core/config/api/useConfig';

import packageJson from '../../../../package.json';

import { OnboardingWelcomeModal } from './OnboardingModal';

const openUrl = (url: string) => {
  // Open in a new tab so the app stays put. window.open(url, '_blank') opens a
  // real tab in Firefox for both https: and mailto: (the OS handler then takes
  // over the throwaway tab). Note: no window features string - passing
  // 'noopener,noreferrer' there made Firefox keep the link in the same tab.
  // window.location.href is avoided because it unloads the current tab on some
  // browsers (observed on Firefox in production).
  const opened = window.open(url, '_blank');
  // Sever the opener link to avoid reverse tabnabbing on http(s) targets.
  if (opened) {
    opened.opener = null;
  }
};

export const OnboardingButton = () => {
  const { t } = useTranslation();
  const { data: config } = useConfig();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);

  const documentationUrl = config?.FRONTEND_DOCUMENTATION_URL;
  const contactEmail = config?.FRONTEND_CONTACT_EMAIL;

  const options: DropdownMenuItem[] = useMemo(() => {
    // Each group is rendered as a block; groups are joined with separators so
    // hiding an item (empty config URL) never leaves a dangling separator.
    const groups: DropdownMenuItem[][] = [];

    const helpGroup: DropdownMenuItem[] = [];
    if (documentationUrl) {
      helpGroup.push({
        label: t('Documentation'),
        icon: <Icon iconName="description" />,
        callback: () => openUrl(documentationUrl),
      });
    }
    helpGroup.push({
      label: t('Onboarding'),
      icon: <Icon iconName="school" />,
      callback: () => setIsOnboardingOpen(true),
    });
    groups.push(helpGroup);

    if (contactEmail) {
      groups.push([
        {
          label: t('Contact us'),
          icon: <Icon iconName="forum" />,
          callback: () => openUrl(`mailto:${contactEmail}`),
        },
      ]);
    }

    groups.push([
      {
        label: t('Latest release'),
        subText: packageJson.version,
        icon: <Icon iconName="history" />,
        isDisabled: true,
      },
    ]);

    return groups.flatMap((group, index) =>
      index === 0 ? group : [{ type: 'separator' }, ...group],
    );
  }, [t, documentationUrl, contactEmail]);

  return (
    <>
      <DropdownMenu
        options={options}
        isOpen={isMenuOpen}
        onOpenChange={setIsMenuOpen}
      >
        <Button
          color="neutral"
          variant="tertiary"
          size="small"
          onClick={() => setIsMenuOpen((prev) => !prev)}
          aria-label={t('Open help menu')}
          icon={<QuestionMarkCircleIcon aria-hidden />}
        />
      </DropdownMenu>

      <OnboardingWelcomeModal
        isOpen={isOnboardingOpen}
        onClose={() => setIsOnboardingOpen(false)}
      />
    </>
  );
};
