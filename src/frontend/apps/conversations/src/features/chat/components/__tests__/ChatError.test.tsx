import { render, screen } from '@testing-library/react';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { ChatError } from '../ChatError';

let mockStatusPageUrl: string | undefined = 'https://status.example.com';

jest.mock('next/router', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('@/core', () => ({
  useConfig: () => ({
    data: { STATUS_PAGE_URL: mockStatusPageUrl },
  }),
}));

describe('ChatError', () => {
  beforeEach(() => {
    mockStatusPageUrl = 'https://status.example.com';
  });
  it('renders generic error with retry button when errorType is generic and has last submission', () => {
    render(
      <ChatError
        errorType="generic"
        hasLastSubmission={true}
        onRetry={jest.fn()}
      />,
      { wrapper: AppWrapper },
    );
    expect(
      screen.getByText('Sorry, an error occurred. Please try again.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders generic error with new conversation button when no last submission', () => {
    render(
      <ChatError
        errorType="generic"
        hasLastSubmission={false}
        onRetry={jest.fn()}
      />,
      { wrapper: AppWrapper },
    );
    expect(
      screen.getByText('Sorry, an error occurred. Please try again.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /start a new conversation/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders model_unavailable message and status page link', () => {
    render(
      <ChatError
        errorType="model_unavailable"
        hasLastSubmission={false}
        onRetry={jest.fn()}
      />,
      { wrapper: AppWrapper },
    );
    expect(
      screen.getByText(
        'The assistant is temporarily unavailable. Please try again later.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /retry/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', mockStatusPageUrl);
  });

  it('renders model_rate_limited message and status page link', () => {
    render(
      <ChatError
        errorType="model_rate_limited"
        hasLastSubmission={false}
        onRetry={jest.fn()}
      />,
      { wrapper: AppWrapper },
    );
    expect(
      screen.getByText(
        'The assistant is overloaded. Please try again in a few minutes.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /retry/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', mockStatusPageUrl);
  });

  it('renders model_connection_error message and status page link', () => {
    render(
      <ChatError
        errorType="model_connection_error"
        hasLastSubmission={false}
        onRetry={jest.fn()}
      />,
      { wrapper: AppWrapper },
    );
    expect(
      screen.getByText(
        'Unable to reach the assistant. Please check your connection or try again later.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /retry/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', mockStatusPageUrl);
  });

  it('renders provider error without status link when statusPageUrl is not configured', () => {
    mockStatusPageUrl = undefined;
    render(
      <ChatError
        errorType="model_unavailable"
        hasLastSubmission={false}
        onRetry={jest.fn()}
      />,
      { wrapper: AppWrapper },
    );
    expect(
      screen.getByText(
        'The assistant is temporarily unavailable. Please try again later.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
