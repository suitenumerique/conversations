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
  label?: string;
  placeholder?: string;
  children?: ReactNode;
};

export const QuickSearch = ({
  onFilter,
  onClear,
  inputContent,
  inputValue,
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
          <Box
            $css={`
              position: sticky;
              top: 0px;
              &:before {
                content: "";
                background-color: #F7F8FA;
                position: absolute;
                width: 100%;
                height: 20px;
                top: -8px;
              }
              &:after {
                content: "";
                position: absolute;
                width: 100%;
                height: 20px;
                bottom: -20px;
                background: linear-gradient(
                  to bottom,
                  #F7F8FA 0%,
                  rgba(247, 248, 250, 0.7) 40%,
                  rgba(255, 255, 255, 0) 100%
                );
              }
              }`}
          >
            <QuickSearchInput
              withSeparator={hasChildrens(children)}
              inputValue={inputValue}
              onFilter={onFilter}
              onClear={onClear}
              placeholder={placeholder}
            >
              {inputContent}
            </QuickSearchInput>
          </Box>
        )}
        <Command.List>
          <Box $padding={{ horizontal: 'xs', top: 'sm' }}>{children}</Box>
        </Command.List>
      </Command>
    </>
  );
};
