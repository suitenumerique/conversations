import { PropsWithChildren, useEffect, useRef, useState } from 'react';
import { css } from 'styled-components';

import { Box, BoxButton, BoxProps, DropButton, Icon, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';

export type DropdownMenuOption = {
  icon?: string;
  label: string;
  testId?: string;
  callback?: () => void | Promise<unknown>;
  danger?: boolean;
  isSelected?: boolean;
  disabled?: boolean;
  show?: boolean;
};

export type DropdownMenuProps = {
  options: DropdownMenuOption[];
  showArrow?: boolean;
  label?: string;
  buttonCss?: BoxProps['$css'];
  disabled?: boolean;
  topMessage?: string;
};

export const DropdownMenu = ({
  options,
  children,
  disabled = false,
  showArrow = false,
  buttonCss,
  label,
  topMessage,
}: PropsWithChildren<DropdownMenuProps>) => {
  const { spacingsTokens } = useCunninghamTheme();
  const [isOpen, setIsOpen] = useState(false);
  const [buttonWidth, setButtonWidth] = useState<number | undefined>(undefined);
  const blockButtonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Mettre à jour la largeur uniquement côté client
    if (blockButtonRef.current) {
      setButtonWidth(blockButtonRef.current.clientWidth);
    }
  }, [isOpen]);

  const onOpenChange = (isOpen: boolean) => {
    setIsOpen(isOpen);
  };

  if (disabled) {
    return children;
  }

  return (
    <DropButton
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      label={label}
      buttonCss={buttonCss}
      button={
        showArrow ? (
          <Box
            ref={blockButtonRef}
            $direction="row"
            $theme="brand"
            $scope="semantic"
            $variation="neutral"
            $align="center"
            $position="relative"
            aria-controls="menu"
          >
            <Box>{children}</Box>
            <Icon
              $css={css`
                color: var(
                  --c--contextuals--content--semantic--brand--tertiary
                );
              `}
              iconName={isOpen ? 'arrow_drop_up' : 'arrow_drop_down'}
            />
          </Box>
        ) : (
          <Box ref={blockButtonRef} aria-controls="menu">
            {children}
          </Box>
        )
      }
    >
      <Box
        $maxWidth="320px"
        $minWidth={buttonWidth ? `${buttonWidth}px` : undefined}
        role="menu"
      >
        {topMessage && (
          <Text
            $theme="brand"
            $variation="tertiary"
            $wrap="wrap"
            $size="xs"
            $weight="bold"
            $padding={{ vertical: 'xs', horizontal: 'base' }}
          >
            {topMessage}
          </Text>
        )}
        {options.map((option, index) => {
          if (option.show !== undefined && !option.show) {
            return;
          }
          const isDisabled = option.disabled !== undefined && option.disabled;
          return (
            <BoxButton
              role="menuitem"
              aria-label={option.label}
              data-testid={option.testId}
              $direction="row"
              disabled={isDisabled}
              tabIndex={isDisabled ? -1 : 0}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onOpenChange?.(false);
                void option.callback?.();
              }}
              key={option.label}
              $align="center"
              $justify="space-between"
              $padding={{ vertical: 'xs', horizontal: 'base' }}
              $width="100%"
              $gap={spacingsTokens['base']}
              $css={css`
                border: none;
                ${index === 0 &&
                css`
                  border-top-left-radius: 4px;
                  border-top-right-radius: 4px;
                `}
                ${index === options.length - 1 &&
                css`
                  border-bottom-left-radius: var(--c--globals--spacings--st);
                  border-bottom-right-radius: var(--c--globals--spacings--st);
                `}
                font-size: var(--c--globals--font--sizes--sm);
                color: var(
                  --c--contextuals--content--semantic--brand--tertiary
                );
                font-weight: var(--c--globals--font--weights--medium);
                cursor: ${isDisabled ? 'not-allowed' : 'pointer'};
                user-select: none;

                &:hover {
                  background-color: var(
                    --c--contextuals--background--semantic--contextual--primary
                  );
                }

                &:focus-visible {
                  outline: 2px solid var(--c--globals--colors--brand-400);
                  outline-offset: -2px;
                  background-color: var(
                    --c--contextuals--background--semantic--contextual--primary
                  );
                }
              `}
            >
              <Box
                $direction="row"
                $align="center"
                $gap={spacingsTokens['base']}
              >
                {option.icon && (
                  <Icon
                    $size="20px"
                    $theme="neutral"
                    $variation={isDisabled ? 'tertiary' : 'primary'}
                    iconName={option.icon}
                    aria-hidden="true"
                  />
                )}
                <Text $variation={isDisabled ? '400' : '1000'}>
                  {option.label}
                </Text>
              </Box>
              {option.isSelected && (
                <Icon iconName="check" $size="20px" aria-hidden="true" />
              )}
            </BoxButton>
          );
        })}
      </Box>
    </DropButton>
  );
};
