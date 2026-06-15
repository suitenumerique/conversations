import { render, screen } from '@testing-library/react';

import { ToolInvocationItem } from '../ToolInvocationItem';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

let mockStatusPageUrl: string | undefined = 'https://status.example.com';

jest.mock('@/core', () => ({
  useConfig: () => ({
    data: { STATUS_PAGE_URL: mockStatusPageUrl },
  }),
}));

const renderResultError = (kind?: string) =>
  render(
    <ToolInvocationItem
      toolInvocation={{
        toolCallId: 'test-id',
        toolName: 'document_parsing',
        state: 'result',
        args: {},
        result: {
          state: 'error',
          ...(kind ? { kind } : {}),
          error: 'whatever',
        },
      }}
    />,
  );

describe('ToolInvocationItem', () => {
  beforeEach(() => {
    mockStatusPageUrl = 'https://status.example.com';
  });

  describe('conversation_resume', () => {
    it('shows the resuming loader when state is call', () => {
      render(
        <ToolInvocationItem
          toolInvocation={{
            toolCallId: 'test-id',
            toolName: 'conversation_resume',
            state: 'call',
            args: {},
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

    it('renders nothing when state is result', () => {
      const { container } = render(
        <ToolInvocationItem
          toolInvocation={{
            toolCallId: 'test-id',
            toolName: 'conversation_resume',
            state: 'result',
            args: {},
            result: { state: 'done' },
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
