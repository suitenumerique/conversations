import clsx from 'clsx';
import { css } from 'styled-components';

import { Text, TextType } from '@/components';

type IconProps = TextType & {
  iconName: string;
  variant?: 'filled' | 'outlined';
};
export const Icon = ({
  iconName,
  variant = 'outlined',
  $theme = 'neutral',
  ...textProps
}: IconProps) => {
  return (
    <Text
      {...textProps}
      aria-hidden="true"
      $theme={$theme}
      className={clsx('--docs--icon-bg', textProps.className, {
        'material-symbols': variant === 'filled',
        'material-symbols-outlined': variant === 'outlined',
      })}
    >
      {iconName}
    </Text>
  );
};

type IconOptionsProps = TextType & {
  isHorizontal?: boolean;
};

export const IconOptions = ({ isHorizontal, ...props }: IconOptionsProps) => {
  return (
    <Icon
      {...props}
      aria-hidden="true"
      iconName={isHorizontal ? 'more_horiz' : 'more_vert'}
      $css={css`
        user-select: none;
        ${props.$css}
      `}
    />
  );
};
