import { SourceUIPart } from '@ai-sdk/ui-utils';
import React from 'react';

import { Box } from '@/components';
import { SourceItem } from '@/features/chat/components/SourceItem';

interface SourceMetadata {
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
    <Box
      $direction="column"
      $padding={{ all: 'sm' }}
      $gap="4px"
      $css={`
       border: 1px solid var(--c--theme--colors--greyscale-100);
       border-radius: 8px;
       margin-top: 0.5rem;
       overflow: hidden;
     `}
    >
      {parts.map((part) => {
        const metadata = getMetadata(part.source.url);
        // Extract title from providerMetadata if available
        const providerTitle = part.source.providerMetadata?.title;
        
        return (
          <SourceItem
            key={part.source.url}
            url={part.source.url}
            metadata={metadata ? {
              ...metadata,
              title: providerTitle || metadata.title
            } : providerTitle ? {
              title: providerTitle,
              favicon: null,
              loading: false,
              error: false
            } : undefined}
          />
        );
      })}
    </Box>
  );
};

SourceItemListComponent.displayName = 'SourceItemList';

export const SourceItemList = React.memo(SourceItemListComponent);
