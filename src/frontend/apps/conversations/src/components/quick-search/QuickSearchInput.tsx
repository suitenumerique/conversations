import { Command } from 'cmdk';
import { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { HorizontalSeparator } from '@/components';
import { useCunninghamTheme } from '@/cunningham';

import { Box } from '../Box';
import { Icon } from '../Icon';
import { Loader } from '../Loader';

type Props = {
  loading?: boolean;
  inputValue?: string;
  onFilter?: (str: string) => void;
  placeholder?: string;
  children?: ReactNode;
  withSeparator?: boolean;
  onClear?: () => void;
};
export const QuickSearchInput = ({
  loading,
  inputValue,
  onFilter,
  placeholder,
  children,
  withSeparator: separator = true,
  onClear,
}: Props) => {
  const { t } = useTranslation();
  const { spacingsTokens } = useCunninghamTheme();

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
          border-radius: 4px;
          margin: 12px 12px 0 12px;
          border: 1px solid #CFD5DE;
          background-color: #EEF1F4;
          padding: 6px 8px;
          &:focus-within {
            border: 2px solid #3E5DE7;
            padding: 5px 7px;
          }
          & input {
            border: none;
            background-color: transparent;
            &:focus {
              border: none;
              outline: none;
            }
          }
        `}
      >
        {!loading && <Icon iconName="search" $variation="600" />}
        {loading && <Loader />}
        <Command.Input
          /* eslint-disable-next-line jsx-a11y/no-autofocus */
          autoFocus={true}
          aria-label={t('Quick search input')}
          value={inputValue}
          role="combobox"
          placeholder={placeholder ?? t('Search')}
          onValueChange={onFilter}
        />
        <Icon
          iconName="close"
          $size="sm"
          $variation="600"
          $css={`cursor: pointer;
            position: absolute;
            opacity: ${inputValue && inputValue.length > 0 && onClear ? 1 : 0}; 
            transition: opacity 0.3s cubic-bezier(1, 0, 0, 1);
            top: 10px;
            right: 10px;
            z-index: 1000;`}
          onClick={onClear}
          aria-label={t('Clear search')}
        />
      </Box>
    </>
  );
};
