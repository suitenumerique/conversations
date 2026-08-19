import { SourceUrlUIPart } from 'ai';
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
  parts: readonly SourceUrlUIPart[];
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
    <Box
      $direction="column"
      $padding={{ all: 'xs' }}
      $gap="4px"
      $css="min-width: 0; width: 100%;"
    >
      {parts.map((part, index) => (
        <SourceItem
          index={index + 1}
          key={part.sourceId}
          url={part.url}
          metadata={getMetadata(part.url)}
        />
      ))}
    </Box>
  );
};

SourceItemListComponent.displayName = 'SourceItemList';

export const SourceItemList = React.memo(SourceItemListComponent);
