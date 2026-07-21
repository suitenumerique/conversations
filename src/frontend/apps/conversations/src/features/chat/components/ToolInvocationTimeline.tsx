import React from 'react';

import { Box } from '@/components';

const CONNECTOR_CSS = `
  width: 2px;
  height: 10px;
  margin-left: 6px;
  border-radius: 1px;
  background: var(--c--contextuals--border--semantic--neutral--tertiary);
`;

interface ToolInvocationTimelineProps {
  children: React.ReactNode;
}

export const ToolInvocationTimeline: React.FC<ToolInvocationTimelineProps> = ({
  children,
}) => {
  const items = React.Children.toArray(children).filter(Boolean);

  if (items.length <= 1) {
    return (
      <Box $direction="column" $gap="4px">
        {items}
      </Box>
    );
  }

  return (
    <Box
      $direction="column"
      data-testid="tool-invocation-timeline"
      aria-label="Tool execution timeline"
    >
      {items.map((item, index) => (
        <React.Fragment key={index}>
          {index > 0 && <Box aria-hidden="true" $css={CONNECTOR_CSS} />}
          <Box $position="relative">{item}</Box>
        </React.Fragment>
      ))}
    </Box>
  );
};
