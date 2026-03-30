import { Loader } from '@gouvfr-lasuite/cunningham-react';
import { Icon } from '@gouvfr-lasuite/ui-kit';
import { Command } from 'cmdk';
import { ReactNode, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { HorizontalSeparator } from '@/components';
import { useCunninghamTheme } from '@/cunningham';

import { Box } from '../Box';

type Props = {
  loading?: boolean;
  inputValue?: string;
  onFilter?: (str: string) => void;
  placeholder?: string;
  children?: ReactNode;
  withSeparator?: boolean;
  listId?: string;
  onUserInteract?: () => void;
  isExpanded?: boolean;
};
export const QuickSearchInput = ({
  loading,
  inputValue,
  onFilter,
  placeholder,
  children,
  withSeparator: separator = true,
  listId,
  onUserInteract,
  isExpanded,
}: Props) => {
  const { t } = useTranslation();
  const { spacingsTokens } = useCunninghamTheme();
  const inputRef = useCallback((node: HTMLInputElement | null) => {
    node?.focus();
  }, []);

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
        className="quick-search-input"
        $gap={spacingsTokens['2xs']}
        $padding={{ horizontal: 'base', bottom: 'sm', top: 'base' }}
      >
        {loading ? (
          <div>
            <Loader size="small" />
          </div>
        ) : (
          <Icon name="search" color="secondary" aria-hidden="true" />
        )}
        <Command.Input
          ref={inputRef}
          aria-label={t('Quick search input')}
          aria-expanded={isExpanded}
          aria-controls={listId}
          onClick={(e) => {
            e.stopPropagation();
            onUserInteract?.();
          }}
          onKeyDown={() => onUserInteract?.()}
          value={inputValue}
          role="combobox"
          placeholder={placeholder ?? t('Search')}
          onValueChange={onFilter}
          maxLength={254}
          data-testid="quick-search-input"
        />
      </Box>
      {separator && <HorizontalSeparator $withPadding={false} />}
    </>
  );
};
