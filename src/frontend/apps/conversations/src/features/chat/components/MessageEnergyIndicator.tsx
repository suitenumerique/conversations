import {
  Button,
  Modal,
  ModalSize,
  Tooltip,
  useModal,
} from '@gouvfr-lasuite/cunningham-react';
import { useTranslation } from 'react-i18next';

import ArrowUpRightIcon from '@/assets/icons/uikit-custom/arrow-up-right.svg';
import LeavesIcon from '@/assets/icons/uikit-custom/leaves.svg';
import { Box, Text } from '@/components';
import { useResponsiveStore } from '@/stores';

const CARBON_IMPACT_DOCS_URL =
  'https://docs.numerique.gouv.fr/docs/7a6e6475-5b8f-4ffb-95ea-198da9ebd6d0/';

const formatCo2Impact = (kgCo2eq: number): string => {
  return `${(kgCo2eq * 1000).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })} g CO₂eq`;
};

interface MessageEnergyIndicatorProps {
  co2ImpactKg: number;
}

export const MessageEnergyIndicator = ({
  co2ImpactKg,
}: MessageEnergyIndicatorProps) => {
  const { t } = useTranslation();
  const { isMobile } = useResponsiveStore();
  const modal = useModal();

  const impactLabel = t('This request: {{co2}}', {
    co2: formatCo2Impact(co2ImpactKg),
  });
  const ariaLabel = t('Carbon impact');

  const button = (
    <Button
      size="nano"
      color="neutral"
      variant="tertiary"
      aria-label={ariaLabel}
      data-testid="message-energy-indicator"
      icon={<LeavesIcon width={14} height={14} aria-hidden />}
      className="c__button--neutral action-chat-button"
      onClick={isMobile ? () => modal.open() : undefined}
    />
  );

  if (isMobile) {
    return (
      <>
        {button}
        <Modal
          closeOnClickOutside
          {...modal}
          title={ariaLabel}
          size={ModalSize.MEDIUM}
          leftActions={
            <Button
              color="neutral"
              variant="bordered"
              href={CARBON_IMPACT_DOCS_URL}
              target="_blank"
              rel="noopener noreferrer"
              icon={<ArrowUpRightIcon width={12} height={12} aria-hidden />}
              iconPosition="right"
            >
               {t('Know more')}
            </Button>
          }
          rightActions={
              <Button
                color="brand"
                variant="primary"
                onClick={() => modal.close()}
              >
                {t('OK')}
              </Button>
          }
        >
          <Text>{impactLabel}</Text>
        </Modal>
      </>
    );
  }

  return (
    <Tooltip placement="top" content={impactLabel}>
      {button}
    </Tooltip>
  );
};
