import { Command } from 'cmdk';
import { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useCunninghamTheme } from '@/cunningham';

import { Box } from '../Box';
import { Text } from '../Text';

import { QuickSearchData } from './QuickSearch';
import { QuickSearchItem } from './QuickSearchItem';

type Props<T> = {
  group: QuickSearchData<T>;
  renderElement?: (element: T) => ReactNode;
  onSelect?: (element: T) => void;
};

export const QuickSearchGroup = <T,>({
  group,
  onSelect,
  renderElement,
}: Props<T>) => {
  const { t } = useTranslation();
  const { spacingsTokens } = useCunninghamTheme();

  return (
    <Box>
      <Command.Group key={group.groupName} forceMount={false}>
        <Text
          $size="sm"
          $variation="700"
          $margin={{ bottom: spacingsTokens['2xs'] }}
          $padding={{ horizontal: 'xs' }}
          $weight="700"
        >
          {t('Search results')}
        </Text>

        {group.startActions?.map((action, index) => {
          return (
            <QuickSearchItem
              key={`${group.groupName}-action-${index}`}
              onSelect={action.onSelect}
            >
              {action.content}
            </QuickSearchItem>
          );
        })}
        {group.elements.map((groupElement, index) => {
          return (
            <QuickSearchItem
              id={`${group.groupName}-element-${index}`}
              key={`${group.groupName}-element-${index}`}
              onSelect={() => {
                onSelect?.(groupElement);
              }}
            >
              {renderElement?.(groupElement)}
            </QuickSearchItem>
          );
        })}
        {group.endActions?.map((action, index) => {
          return (
            <QuickSearchItem
              key={`${group.groupName}-action-${index}`}
              onSelect={action.onSelect}
            >
              {action.content}
            </QuickSearchItem>
          );
        })}
        {group.emptyString && group.elements.length === 0 && (
          <Text
            $size="sm"
            $variation="500"
            $margin={{ bottom: spacingsTokens['2xs'] }}
            $padding={{ horizontal: 'xs' }}
          >
            {group.emptyString}
          </Text>
        )}
      </Command.Group>
    </Box>
  );
};
