import { SourceUIPart } from '@ai-sdk/ui-utils';
import React from 'react';

import { Box } from '@/components';
import { SourceItem } from '@/features/chat/components/SourceItem';

interface SourceItemListProps {
  parts: readonly SourceUIPart[];
}

export const SourceItemList: React.FC<SourceItemListProps> = ({ parts }) => {
  if (parts.length === 0) {
    return null;
  }

  return (
    <Box
      $direction="column"
      $padding={{ all: 'sm' }}
      $gap="4px"
      $css={`
       border: 1px solid var(--c--theme--colors--greyscale-200);
       border-radius: 8px;
       margin-top: 0.5rem;
       overflow: hidden;
     `}
    >
      {parts.map((part) => (
        <SourceItem key={part.source.url} url={part.source.url} />
      ))}
    </Box>
  );
};
