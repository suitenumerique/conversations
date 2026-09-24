import { Box, Text, ToggleSwitch } from '@/components';

interface SettingsToggleRowProps {
  title: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
  'aria-label': string;
}

export const SettingsToggleRow = ({
  title,
  description,
  checked,
  disabled,
  onToggle,
  'aria-label': ariaLabel,
}: SettingsToggleRowProps) => (
  <Box>
    <Text $size="md" $weight="500" $theme="greyscale" $variation="850">
      {title}
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
          {description}
        </Text>
      </Box>
      <ToggleSwitch
        checked={checked}
        onChange={onToggle}
        disabled={disabled}
        aria-label={ariaLabel}
      />
    </Box>
  </Box>
);
