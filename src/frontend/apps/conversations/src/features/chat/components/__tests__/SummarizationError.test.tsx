import { fireEvent, render, screen } from '@testing-library/react';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { SummarizationError } from '../SummarizationError';

describe('SummarizationError', () => {
  it('renders the failure message and a retry button', () => {
    render(<SummarizationError onRetry={jest.fn()} />, { wrapper: AppWrapper });

    expect(
      screen.getByText('Summarization failed. Please try again later.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('calls onRetry when the retry button is clicked', () => {
    const onRetry = jest.fn();
    render(<SummarizationError onRetry={onRetry} />, { wrapper: AppWrapper });

    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
