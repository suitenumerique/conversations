import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ToolCard } from '../ToolCard';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/components', () => ({
  Box: ({
    children,
    as: Component = 'div',
    ...props
  }: {
    children?: React.ReactNode;
    as?: React.ElementType;
    [key: string]: unknown;
  }) => {
    const Tag = Component;
    return <Tag {...props}>{children}</Tag>;
  },
  Icon: ({ iconName }: { iconName: string }) => (
    <span data-testid={`icon-${iconName}`} />
  ),
  Loader: () => <div role="status" data-testid="assistant-loader" />,
  Text: ({ children }: { children?: React.ReactNode }) => (
    <span>{children}</span>
  ),
}));

describe('ToolCard', () => {
  it('shows only the tool name and loading state when collapsed', () => {
    render(
      <ToolCard
        toolInvocation={{
          toolCallId: 'call-1',
          toolName: 'web_search',
          state: 'call',
          args: { query: 'latest news' },
        }}
      />,
    );

    expect(screen.getByText('Web search')).toBeInTheDocument();
    expect(screen.queryByText(/Searching the web/)).not.toBeInTheDocument();
    expect(screen.queryByText('Request')).not.toBeInTheDocument();
    expect(screen.getByTestId('assistant-loader')).toBeInTheDocument();
  });

  it('shows only the tool name and success state when collapsed', () => {
    render(
      <ToolCard
        toolInvocation={{
          toolCallId: 'call-3',
          toolName: 'summarize',
          state: 'result',
          args: { instructions: 'In 2 paragraphs' },
          result: 'This is a short summary for the user.',
        }}
      />,
    );

    expect(screen.getByText('Summarize')).toBeInTheDocument();
    expect(
      screen.queryByText(/This is a short summary for the user./),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('icon-check_circle')).toBeInTheDocument();
  });

  it('shows readable details only when expanded', async () => {
    const user = userEvent.setup();

    render(
      <ToolCard
        toolInvocation={{
          toolCallId: 'call-2',
          toolName: 'web_search',
          state: 'result',
          args: { query: 'latest news' },
          result: {
            '0': { title: 'Result 1', url: 'https://example.com/1' },
            '1': { title: 'Result 2', url: 'https://example.com/2' },
          },
        }}
      />,
    );

    expect(screen.queryByText('Preview')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Toggle tool details' }));

    expect(screen.getByText('Request')).toBeInTheDocument();
    expect(screen.getByText('Query: latest news')).toBeInTheDocument();
    expect(screen.getByText('Preview')).toBeInTheDocument();
    expect(screen.getByText(/Result 1/)).toBeInTheDocument();
    expect(screen.queryByText(/"title"/)).not.toBeInTheDocument();
  });

  it('shows error details only when expanded', async () => {
    const user = userEvent.setup();

    render(
      <ToolCard
        toolInvocation={{
          toolCallId: 'call-4',
          toolName: 'web_search',
          state: 'result',
          args: { query: 'fail' },
          result: { state: 'error', error: 'Provider unavailable' },
        }}
      />,
    );

    expect(screen.getByText('Web search')).toBeInTheDocument();
    expect(screen.queryByText(/Provider unavailable/)).not.toBeInTheDocument();
    expect(screen.getByTestId('icon-error')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Toggle tool details' }));

    expect(screen.getByText('Provider unavailable')).toBeInTheDocument();
  });
});
