import { ReactNode } from 'react';

import { Box, Tabs } from '@/components';

interface SidebarModalLayoutItem {
  id: string;
  label: string;
}

interface SidebarModalLayoutProps {
  title: string;
  items: SidebarModalLayoutItem[];
  activeItemId: string;
  onItemSelect: (id: string) => void;
  children: ReactNode;
  'aria-label': string;
}

export const SidebarModalLayout = ({
  title,
  items,
  activeItemId,
  onItemSelect,
  children,
  'aria-label': ariaLabel,
}: SidebarModalLayoutProps) => {
  const stopModalOutsideClose = (event: React.MouseEvent) => {
    event.stopPropagation();
  };

  return (
    <Box
      aria-label={ariaLabel}
      $direction="row"
      $gap="16px"
      $align="stretch"
      onMouseDown={stopModalOutsideClose}
      onClick={stopModalOutsideClose}
    >
      <Box
        $css={`
          min-width: 200px;
          min-height: calc(100% + 48px);
          margin-top: -24px;
          margin-left: -24px;
          margin-bottom: -24px;
          border-right: 1px solid var(--c--contextuals--border--surface--primary);
          margin-right: var(--c--theme--spacings--sm);
          background-color: var(--c--contextuals--background--semantic--neutral--tertiary);
        `}
      >
      <Box $padding={{horizontal: 'base'}}>
        <h3
          style={{
            fontSize: 'var(--c--globals--font--sizes--lg)',
            fontWeight: 700,
            minWidth: '200px',
            paddingLeft: 'var(--c--globals--spacings--xxs)',
            marginBottom: 'var(--c--globals--spacings--sm)',
            color: 'var(--c--contextuals--content--semantic--neutral--primary)',
          }}
        >
          {title}
        </h3>
        <Box>
          <Tabs
            tabs={items}
            selectedTab={activeItemId}
            onSelectionChange={onItemSelect}
          />
        </Box>
      </Box>
      </Box>

      <Box $justify="space-between" $css="width: 100%;">
        {children}
      </Box>
    </Box>
  );
};
