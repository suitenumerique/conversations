import { Box } from './Box';
import { Icon } from './Icon';

interface ToggleSwitchProps {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  'aria-label'?: string;
}

export const ToggleSwitch = ({
  checked,
  onChange,
  disabled = false,
  'aria-label': ariaLabel,
}: ToggleSwitchProps) => {
  return (
    <Box $css="padding-top: 2px;">
      <Box
        $css={`
          position: relative;
          width: 44px;
          height: 24px;
          background-color: ${checked ? 'var(--c--contextuals--content--semantic--brand--tertiary)' : 'var(--c--contextuals--content--semantic--neutral--tertiary)'};
          border-radius: 12px;
          cursor: ${disabled ? 'not-allowed' : 'pointer'};
          transition: all 0.2s ease;
          opacity: ${disabled ? 0.6 : 1};
        `}
        onClick={disabled ? undefined : onChange}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (!disabled) {
              onChange();
            }
          }
        }}
        role="switch"
        aria-checked={checked}
        aria-label={ariaLabel}
        aria-disabled={disabled}
        tabIndex={disabled ? -1 : 0}
      >
        <Box
          $css={`
            position: absolute;
            top: 2px;
            left: ${checked ? '22px' : '2px'};
            width: 20px;
            height: 20px;
            background-color: white;
            border-radius: 50%;
            transition: left 0.2s ease;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            display: flex;
            align-items: center;
            justify-content: center;
          `}
        >
          <Icon
            iconName={checked ? 'check' : ''}
            $size="12px"
            $theme="brand"
            $variation="tertiary"
          />
        </Box>
      </Box>
    </Box>
  );
};
