import { Button, Modal, ModalSize } from '@gouvfr-lasuite/cunningham-react';
import React, { ComponentType, SVGProps, useState } from 'react';
import { useTranslation } from 'react-i18next';

import WarningFilledIcon from '@/assets/icons/uikit-custom/warning-filled.svg';
import { Box, Icon, Text } from '@/components';
import { BannerLevel, StatusBanner } from '@/core/config/api/useConfig';

type LevelStyle = {
  background: string;
  border: string;
  foreground: string;
  IconComponent?: ComponentType<SVGProps<SVGSVGElement>>;
};

const LEVEL_STYLES: Record<BannerLevel, LevelStyle> = {
  info: {
    background: 'var(--c--contextuals--background--semantic--info--tertiary)',
    border: 'var(--c--contextuals--border--semantic--info--tertiary)',
    foreground: 'var(--c--contextuals--content--semantic--info--primary)',
  },
  warning: {
    background:
      'var(--c--contextuals--background--semantic--warning--tertiary)',
    border: 'var(--c--contextuals--border--semantic--warning--tertiary)',
    foreground: 'var(--c--contextuals--content--semantic--warning--primary)',
    IconComponent: WarningFilledIcon,
  },
  alert: {
    background: 'var(--c--contextuals--background--semantic--error--tertiary)',
    border: 'var(--c--contextuals--border--semantic--error--tertiary)',
    foreground: 'var(--c--contextuals--content--semantic--error--primary)',
    IconComponent: WarningFilledIcon,
  },
};

export const Banner = ({ level, title, content }: StatusBanner) => {
  const { t } = useTranslation();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const style = LEVEL_STYLES[level] ?? LEVEL_STYLES.info;
  const hasContent = Boolean(content);

  return (
    <>
      <Box
        as={hasContent ? 'button' : 'div'}
        $align="center"
        $direction="row"
        $gap="8px"
        onClick={hasContent ? () => setIsModalOpen(true) : undefined}
        onKeyDown={
          hasContent
            ? (e: React.KeyboardEvent) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setIsModalOpen(true);
                }
              }
            : undefined
        }
        aria-label={hasContent ? t('Show banner details') : undefined}
        $css={`
          height: 40px;
          padding: 8px;
          border-radius: 8px;
          border: 1px solid ${style.border};
          background: ${style.background};
          box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.05);
          color: ${style.foreground};
          width: fit-content;
          max-width: min(100%, 600px);
          font: inherit;
          ${hasContent ? 'cursor: pointer;' : ''}
        `}
        className="--docs--status-banner"
        role={hasContent ? undefined : 'status'}
      >
        {style.IconComponent && (
          <style.IconComponent
            data-testid="banner-icon"
            width={20}
            height={20}
          />
        )}
        <Text $css={`color: ${style.foreground};`}>{title}</Text>
        {hasContent && (
          <Icon
            iconName="info"
            $css={`color: ${style.foreground}; display: block; line-height: 1;`}
            $size="20px"
          />
        )}
      </Box>
      {isModalOpen && (
        <Modal
          isOpen
          closeOnClickOutside
          onClose={() => setIsModalOpen(false)}
          aria-label={t('Status banner details')}
          size={ModalSize.SMALL}
          title={
            <Text
              $size="h6"
              as="h6"
              $margin={{ all: '0' }}
              $align="flex-start"
              $variation="1000"
            >
              {t('What is happening?')}
            </Text>
          }
          rightActions={
            <Button
              color="brand"
              variant="primary"
              onClick={() => setIsModalOpen(false)}
            >
              {t('I understand')}
            </Button>
          }
        >
          <Text $size="sm" $variation="600" $css="white-space: pre-wrap;">
            {content}
          </Text>
        </Modal>
      )}
    </>
  );
};
