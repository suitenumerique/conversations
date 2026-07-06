import {
  Button,
  Modal,
  ModalSize,
  Tooltip,
  useModal,
} from '@gouvfr-lasuite/cunningham-react';
import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import ArrowUpRightIcon from '@/assets/icons/uikit-custom/arrow-up-right.svg';
import LeavesIcon from '@/assets/icons/uikit-custom/leaves.svg';
import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useResponsiveStore } from '@/stores';

import {
  buildImpactCo2ComparateurUrl,
  buildImpactCo2WidgetDataSearch,
  mountImpactCo2Widget,
} from '../utils/impactCo2';

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
  const { t, i18n } = useTranslation();
  const { isMobile } = useResponsiveStore();
  const theme = useCunninghamTheme((state) => state.theme);
  const modal = useModal();

  const impactLabel = t('This request: {{co2}}', {
    co2: formatCo2Impact(co2ImpactKg),
  });
  const ariaLabel = t('Carbon impact');

  const comparateurUrl = useMemo(
    () => buildImpactCo2ComparateurUrl(co2ImpactKg),
    [co2ImpactKg],
  );

  const dataSearch = useMemo(() => {
    const widgetTheme =
      theme === 'dark' || theme === 'dsfr-dark' ? 'night' : 'default';
    const language = i18n.resolvedLanguage?.startsWith('fr') ? 'fr' : 'en';
    return buildImpactCo2WidgetDataSearch({
      co2ImpactKg,
      language,
      theme: widgetTheme,
    });
  }, [co2ImpactKg, theme, i18n.resolvedLanguage]);

  const widgetContainerRef = useCallback(
    (container: HTMLDivElement | null) => {
      if (!container) {
        return;
      }
      mountImpactCo2Widget(container, dataSearch);
    },
    [dataSearch],
  );

  const button = (
    <Button
      size="nano"
      color="neutral"
      variant="tertiary"
      aria-label={ariaLabel}
      data-testid="message-energy-indicator"
      icon={<LeavesIcon width={14} height={14} aria-hidden />}
      className="c__button--neutral action-chat-button"
      onClick={() => modal.open()}
    />
  );

  return (
    <>
      {isMobile ? (
        button
      ) : (
        <Tooltip placement="top" content={impactLabel}>
          {button}
        </Tooltip>
      )}
      <Modal
        closeOnClickOutside
        {...modal}
        title={ariaLabel}
        size={ModalSize.MEDIUM}
        leftActions={
          <Button
            color="neutral"
            variant="bordered"
            href={comparateurUrl}
            target="_blank"
            rel="noopener noreferrer"
            icon={<ArrowUpRightIcon aria-hidden />}
            iconPosition="right"
          >
            {t('Know more')}
          </Button>
        }
        rightActions={
          <Button color="brand" variant="primary" onClick={() => modal.close()}>
            {t('OK')}
          </Button>
        }
      >
        <Box>
          <Text>{impactLabel}</Text>
          <div
            ref={widgetContainerRef}
            data-testid="impact-co2-widget"
            style={{ width: '100%', minHeight: '120px' }}
          />
        </Box>
      </Modal>
    </>
  );
};
