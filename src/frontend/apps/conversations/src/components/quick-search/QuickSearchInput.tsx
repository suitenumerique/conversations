import { Command } from 'cmdk';
import { ReactNode, useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { HorizontalSeparator } from '@/components';
import { useCunninghamTheme } from '@/cunningham';

import { Box } from '../Box';
import { Icon } from '../Icon';

type Props = {
  inputValue?: string;
  onFilter?: (str: string) => void;
  placeholder?: string;
  children?: ReactNode;
  withSeparator?: boolean;
  onClear?: () => void;
};
export const QuickSearchInput = ({
  inputValue,
  onFilter,
  placeholder,
  children,
  withSeparator: separator = true,
  onClear,
}: Props) => {
  const { t } = useTranslation();
  const { spacingsTokens } = useCunninghamTheme();

  const [localValue, setLocalValue] = useState(inputValue || '');

  const debouncedFilter = useCallback(
    (value: string) => {
      let timeoutId: NodeJS.Timeout;

      const debounce = () => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => {
          onFilter?.(value);
        }, 150);
      };

      debounce();
    },
    [onFilter],
  );

  const handleChange = useCallback(
    (value: string) => {
      setLocalValue(value);
      debouncedFilter(value);
    },
    [debouncedFilter],
  );

  const handleClear = useCallback(() => {
    setLocalValue('');
    onClear?.();
  }, [onClear]);

  if (children) {
    return (
      <>
        {children}
        {separator && <HorizontalSeparator />}
      </>
    );
  }

  return (
    <>
      <Box
        $direction="row"
        $align="center"
        $gap={spacingsTokens['2xs']}
        $css={`
          position: relative;
          justify-content: space-between;
          border-radius: 4px;
          margin: 12px 12px 0 12px;
          border: 1px solid #CFD5DE;
          background-color: #eff1f5;
          padding: 6px 8px;
          &:focus-within, &:hover {
            border: 2px solid #3E5DE7;
            padding: 5px 7px;
          }
          & input {
            font-family: 'Marianne' !important;
            border: none;
            font-size: 0.9rem;
            font-weight: 400;
            background-color: transparent;
            &:focus {
              border: none;
              outline: none;
            }
          }
        `}
      >
        <Box $direction="row" $gap="6px">
          <Icon iconName="search" $variation="600" />
          <Command.Input
            aria-label={t('Quick search input')}
            value={localValue}
            role="combobox"
            placeholder={placeholder ?? t('Search')}
            onValueChange={handleChange}
          />
        </Box>
        <Box
          onClick={handleClear}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleClear();
            }
          }}
          role="button"
          tabIndex={0}
          aria-label={t('Clear search')}
          $css={`cursor: pointer;
              opacity: ${localValue && localValue.length > 0 && onClear ? 1 : 0}; 
              transition: opacity 0.3s cubic-bezier(1, 0, 0, 1);
              right: 10px;
              border-radius: 4px;
              padding: 7px;
              background-color: #e4e6ea;
              z-index: 1000;
              &:focus {
                outline: 2px solid #3E5DE7;
                outline-offset: 2px;
              }`}
        >
          <Icon iconName="close" $size="15px" $variation="600" />
        </Box>
      </Box>
    </>
  );
};
