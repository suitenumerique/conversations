import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ToolInvocationItem } from '../ToolInvocationItem';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

let mockStatusPageUrl: string | undefined = 'https://status.example.com';

vi.mock('@/core', () => ({
  useConfig: () => ({
    data: { STATUS_PAGE_URL: mockStatusPageUrl },
  }),
}));

const renderResultError = (kind?: string) =>
  render(
    <ToolInvocationItem
      toolInvocation={{
        type: 'tool-document_parsing',
        toolCallId: 'test-id',
        state: 'output-available',
        input: {},
        output: {
          state: 'error',
          ...(kind ? { kind } : {}),
          error: 'whatever',
        },
      }}
    />,
  );

const CHART = {
  type: 'bar',
  title: 'Sales per region',
  labels: ['Nord', '<img src=x onerror=alert(1)>'],
  series: [{ name: 'montant_sum', values: [1002.5, 4] }],
  total: 2,
};

const renderQueryTable = (output: unknown) =>
  render(
    <ToolInvocationItem
      toolInvocation={{
        type: 'tool-query_table',
        toolCallId: 'test-id',
        state: 'output-available',
        input: {},
        output,
      }}
    />,
  );

describe('ToolInvocationItem', () => {
  beforeEach(() => {
    mockStatusPageUrl = 'https://status.example.com';
  });

  describe('query_table', () => {
    it('shows the chart title and its data on demand', async () => {
      renderQueryTable({ chart: CHART });

      expect(screen.getByText('Sales per region')).toBeInTheDocument();
      expect(screen.queryByRole('table')).not.toBeInTheDocument();

      await userEvent.click(screen.getByRole('button', { name: 'Show data' }));

      const table = screen.getByRole('table');
      expect(table).toHaveTextContent('montant_sum');
      expect(table).toHaveTextContent('1,002.5');
      // Cell text from the file is rendered as text, never as markup.
      expect(
        screen.getByText('<img src=x onerror=alert(1)>'),
      ).toBeInTheDocument();
      expect(within(table).queryByRole('img')).not.toBeInTheDocument();
    });

    it('offers to download the chart as an image', () => {
      renderQueryTable({ chart: CHART });

      expect(
        screen.getByRole('button', { name: 'Download chart' }),
      ).toBeInTheDocument();
    });

    it('says when the chart only covers part of the result', () => {
      renderQueryTable({ chart: { ...CHART, total: 340 } });

      expect(
        screen.getByText(
          'The chart shows the first {{shown}} of {{total}} rows.',
        ),
      ).toBeInTheDocument();
    });

    it('renders nothing for a result without chart', () => {
      const { container } = renderQueryTable('| region | count |');

      expect(container).toBeEmptyDOMElement();
    });

    it('renders nothing for a malformed chart', () => {
      const { container } = renderQueryTable({
        chart: { ...CHART, type: 'scatter' },
      });

      expect(container).toBeEmptyDOMElement();
    });

    it('renders nothing before the output is available', () => {
      const { container } = render(
        <ToolInvocationItem
          toolInvocation={{
            type: 'tool-query_table',
            toolCallId: 'test-id',
            state: 'input-available',
            input: {},
          }}
        />,
      );

      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('conversation_resume', () => {
    it('shows the resuming loader when the input is available', () => {
      render(
        <ToolInvocationItem
          toolInvocation={{
            type: 'tool-conversation_resume',
            toolCallId: 'test-id',
            state: 'input-available',
            input: {},
          }}
        />,
      );

      expect(
        screen.getByText('Picking up where you left off'),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          'Bringing this conversation and its documents back. This may take a moment longer than usual.',
        ),
      ).toBeInTheDocument();
    });

    it('renders nothing when the output is available', () => {
      const { container } = render(
        <ToolInvocationItem
          toolInvocation={{
            type: 'tool-conversation_resume',
            toolCallId: 'test-id',
            state: 'output-available',
            input: {},
            output: { state: 'done' },
          }}
        />,
      );

      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('document_parsing errors', () => {
    it('renders rag_unavailable message with a status page link', () => {
      renderResultError('rag_unavailable');

      expect(
        screen.getByText(
          'Document processing is temporarily unavailable. Please try again later.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole('link')).toHaveAttribute(
        'href',
        mockStatusPageUrl,
      );
    });

    it('renders rag_busy message with a status page link', () => {
      renderResultError('rag_busy');

      expect(
        screen.getByText(
          'The document service is too busy. Please try again later.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole('link')).toBeInTheDocument();
    });

    it('renders rag_rate_limited message with a status page link', () => {
      renderResultError('rag_rate_limited');

      expect(
        screen.getByText(
          'Too many document requests. Please try again in a few minutes.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole('link')).toBeInTheDocument();
    });

    it('renders rag_connection_error message with a status page link', () => {
      renderResultError('rag_connection_error');

      expect(
        screen.getByText(
          'Unable to reach the document service. Please try again later.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole('link')).toBeInTheDocument();
    });

    it('renders rag_internal_error message without a status link', () => {
      renderResultError('rag_internal_error');

      expect(
        screen.getByText(
          'We encountered an internal error. Our team has been alerted.',
        ),
      ).toBeInTheDocument();
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('renders rag_error message without a status link', () => {
      renderResultError('rag_error');

      expect(
        screen.getByText(
          'Your document could not be processed. Please try again.',
        ),
      ).toBeInTheDocument();
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('falls back to the generic rag_error message when kind is missing', () => {
      renderResultError(undefined);

      expect(
        screen.getByText(
          'Your document could not be processed. Please try again.',
        ),
      ).toBeInTheDocument();
    });

    it('falls back to the generic rag_error message when kind is unknown', () => {
      renderResultError('rag_meow');

      expect(
        screen.getByText(
          'Your document could not be processed. Please try again.',
        ),
      ).toBeInTheDocument();
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('renders concurrent_reindex message without a status link', () => {
      renderResultError('concurrent_reindex');

      expect(
        screen.getByText(
          'Documents are currently being re-indexed. Please retry in a moment.',
        ),
      ).toBeInTheDocument();
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('omits the status link when STATUS_PAGE_URL is not configured', () => {
      mockStatusPageUrl = undefined;
      renderResultError('rag_unavailable');

      expect(
        screen.getByText(
          'Document processing is temporarily unavailable. Please try again later.',
        ),
      ).toBeInTheDocument();
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });
  });
});
