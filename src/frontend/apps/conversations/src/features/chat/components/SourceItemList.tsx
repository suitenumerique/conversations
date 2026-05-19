import { SourceUIPart } from '@ai-sdk/ui-utils';
import React from 'react';

import { Box } from '@/components';
import { SourceItem } from '@/features/chat/components/SourceItem';

export interface SourceMetadata {
  title: string | null;
  favicon: string | null;
  loading: boolean;
  error: boolean;
}

interface SourceItemListProps {
  parts: readonly SourceUIPart[];
  getMetadata: (url: string) => SourceMetadata | undefined;
}

const SourceItemListComponent: React.FC<SourceItemListProps> = ({
  parts,
  getMetadata,
}) => {
  if (parts.length === 0) {
    return null;
  }
  return (
    <Box $direction="column" $padding={{ all: 'xs' }} $gap="4px">
      {parts.map((part, index) => (
        <SourceItem
          index={index + 1}
          key={part.source.url}
          url={part.source.url}
          metadata={getMetadata(part.source.url)}
        />
      ))}
    </Box>
  );
};

SourceItemListComponent.displayName = 'SourceItemList';

export const SourceItemList = React.memo(SourceItemListComponent);
