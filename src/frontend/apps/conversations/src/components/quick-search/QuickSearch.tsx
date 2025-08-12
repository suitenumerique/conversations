import { Command } from 'cmdk';
import { ReactNode, useRef } from 'react';

import { hasChildrens } from '@/utils/children';

import { Box } from '../Box';

import { QuickSearchInput } from './QuickSearchInput';
import { QuickSearchStyle } from './QuickSearchStyle';

export type QuickSearchAction = {
  onSelect?: () => void;
  content: ReactNode;
};

export type QuickSearchData<T> = {
  groupName: string;
  elements: T[];
  emptyString?: string;
  startActions?: QuickSearchAction[];
  endActions?: QuickSearchAction[];
  showWhenEmpty?: boolean;
};

export type QuickSearchProps = {
  onFilter?: (str: string) => void;
  onClear?: () => void;
  inputValue?: string;
  inputContent?: ReactNode;
  showInput?: boolean;
  loading?: boolean;
  label?: string;
  placeholder?: string;
  children?: ReactNode;
};

export const QuickSearch = ({
  onFilter,
  onClear,
  inputContent,
  inputValue,
  loading,
  showInput = true,
  label,
  placeholder,
  children,
}: QuickSearchProps) => {
  const ref = useRef<HTMLDivElement | null>(null);

  return (
    <>
      <QuickSearchStyle />
      <Command label={label} shouldFilter={false} ref={ref}>
        {showInput && (
          <QuickSearchInput
            loading={loading}
            withSeparator={hasChildrens(children)}
            inputValue={inputValue}
            onFilter={onFilter}
            onClear={onClear}
            placeholder={placeholder}
          >
            {inputContent}
          </QuickSearchInput>
        )}
        <Command.List>
          <Box $padding={{ horizontal: 'sm', top: 'sm' }}>{children}</Box>
        </Command.List>
      </Command>
    </>
  );
};
