import { Button, Tooltip } from '@gouvfr-lasuite/cunningham-react';
import { useTranslation } from 'react-i18next';

import LeavesIcon from '@/assets/icons/uikit-custom/leaves.svg';

import { formatCo2Impact } from '../utils/formatCo2Impact';

interface MessageEnergyIndicatorProps {
  co2ImpactKg: number;
}

export const MessageEnergyIndicator = ({
  co2ImpactKg,
}: MessageEnergyIndicatorProps) => {
  const { t } = useTranslation();

  return (
    <Tooltip
      placement="top"
      data-testid="message-energy-indicator"
      content={t('Estimated carbon footprint for this generation: {{co2}}', {
        co2: formatCo2Impact(co2ImpactKg),
      })}
    >
      <Button
        size="small"
        color="neutral"
        variant="tertiary"
        aria-label={t('Energy impact for this message')}
        icon={
          <LeavesIcon
            width={14}
            height={14}
            aria-hidden
            style={{
              display: 'block',
              color:
                'var(--c--contextuals--content--semantic--neutral--secondary)',
            }}
          />
        }
        className="c__button--neutral c__button--neutral--icon action-chat-button"
      />
    </Tooltip>
  );
};
