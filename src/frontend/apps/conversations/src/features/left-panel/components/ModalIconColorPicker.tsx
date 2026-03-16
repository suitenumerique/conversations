import { Modal, ModalSize } from '@openfun/cunningham-react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box } from '@/components';
import { useCunninghamTheme } from '@/cunningham';

import { PROJECT_COLORS, PROJECT_ICONS } from './project-constants';

const iconEntries = Object.entries(PROJECT_ICONS);
const colorEntries = Object.entries(PROJECT_COLORS);

const gridCss = css`
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
  justify-items: center;
`;

const iconCellCss = css`
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  border: none;
  background-color: transparent;
  color: var(--c--contextuals--content--semantic--neutral--secondary);
  transition: background-color 0.15s ease;

  & svg {
    fill: currentColor;
  }

  &:hover {
    background-color: var(
      --c--contextuals--background--semantic--overlay--primary
    );
  }
`;

const iconSelectedCss = css`
  ${iconCellCss}
  background-color: var(
    --c--contextuals--background--semantic--overlay--primary
  );
`;

const colorCellCss = css`
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  border: none;
  background-color: transparent;
  transition: background-color 0.15s ease;

  &:hover {
    background-color: var(
      --c--contextuals--background--semantic--overlay--primary
    );
  }
`;

const colorSelectedCss = css`
  ${colorCellCss}
  background-color: var(
    --c--contextuals--background--semantic--overlay--primary
  );
`;

const separatorCss = css`
  height: 1px;
  background-color: var(--c--contextuals--border--semantic--neutral--default);
`;

interface ModalIconColorPickerProps {
  icon: string;
  color: string;
  onIconChange: (icon: string) => void;
  onColorChange: (color: string) => void;
  onClose: () => void;
}

export const ModalIconColorPicker = ({
  icon,
  color,
  onIconChange,
  onColorChange,
  onClose,
}: ModalIconColorPickerProps) => {
  const { t } = useTranslation();
  const { colorsTokens } = useCunninghamTheme();

  return (
    <Modal
      isOpen
      closeOnClickOutside
      onClose={onClose}
      aria-label={t('Choose icon and color')}
      size={ModalSize.SMALL}
    >
      <Box $direction="column" $gap="sm" $padding={{ all: 'xs' }}>
        <Box $css={gridCss}>
          {iconEntries.map(([key, IconComp]) => (
            <Box
              key={key}
              as="button"
              type="button"
              $css={icon === key ? iconSelectedCss : iconCellCss}
              onClick={() => onIconChange(key)}
              aria-label={key}
              aria-pressed={icon === key}
            >
              <IconComp width={24} height={24} />
            </Box>
          ))}
        </Box>

        <Box $css={separatorCss} />

        <Box $css={gridCss}>
          {colorEntries.map(([key, token]) => (
            <Box
              key={key}
              as="button"
              type="button"
              $css={color === key ? colorSelectedCss : colorCellCss}
              onClick={() => onColorChange(key)}
              aria-label={key}
              aria-pressed={color === key}
            >
              <Box
                $css={css`
                  width: 32px;
                  height: 32px;
                  border-radius: 50%;
                `}
                style={{
                  backgroundColor:
                    colorsTokens[token as keyof typeof colorsTokens],
                }}
              />
            </Box>
          ))}
        </Box>
      </Box>
    </Modal>
  );
};
