import { render, screen } from '@testing-library/react';

import { ToolInvocationTimeline } from '../ToolInvocationTimeline';
import { ToolCard } from '../ToolCard';

jest.mock('../ToolCard', () => ({
  ToolCard: ({ toolInvocation }: { toolInvocation: { toolCallId: string } }) => (
    <div data-testid={`tool-card-${toolInvocation.toolCallId}`} />
  ),
}));

jest.mock('@/components', () => ({
  Box: ({
    children,
    ...props
  }: {
    children?: React.ReactNode;
    [key: string]: unknown;
  }) => <div {...props}>{children}</div>,
}));

describe('ToolInvocationTimeline', () => {
  it('does not render a connector for a single tool', () => {
    render(
      <ToolInvocationTimeline>
        <ToolCard
          toolInvocation={{
            toolCallId: 'call-1',
            toolName: 'web_search',
            state: 'call',
            args: {},
          }}
        />
      </ToolInvocationTimeline>,
    );

    expect(screen.queryByTestId('tool-invocation-timeline')).not.toBeInTheDocument();
    expect(screen.getByTestId('tool-card-call-1')).toBeInTheDocument();
  });

  it('renders vertical connectors between multiple tools', () => {
    const { container } = render(
      <ToolInvocationTimeline>
        <ToolCard
          toolInvocation={{
            toolCallId: 'call-1',
            toolName: 'web_search',
            state: 'result',
            args: {},
            result: {},
          }}
        />
        <ToolCard
          toolInvocation={{
            toolCallId: 'call-2',
            toolName: 'summarize',
            state: 'call',
            args: {},
          }}
        />
      </ToolInvocationTimeline>,
    );

    expect(screen.getByTestId('tool-invocation-timeline')).toBeInTheDocument();
    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(1);
  });
});
