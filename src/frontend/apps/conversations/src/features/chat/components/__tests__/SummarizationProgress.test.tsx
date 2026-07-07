import { act, render, screen } from '@testing-library/react';

import { SummarizationProgress } from '../SummarizationProgress';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('SummarizationProgress', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders the label and starts near zero', () => {
    render(<SummarizationProgress done={false} />);

    expect(screen.getByText('Summarizing conversation...')).toBeInTheDocument();
    const fill = screen.getByTestId('summarization-progress-fill');
    expect(parseInt(fill.style.width, 10)).toBeLessThanOrEqual(5);
  });

  it('advances along the logarithmic curve without reaching 100%', () => {
    render(<SummarizationProgress done={false} />);

    act(() => {
      jest.advanceTimersByTime(8000); // one time constant
    });
    const fill = screen.getByTestId('summarization-progress-fill');
    const afterOneTau = parseInt(fill.style.width, 10);
    expect(afterOneTau).toBeGreaterThan(50); // ~60% at t = τ
    expect(afterOneTau).toBeLessThan(95);

    act(() => {
      jest.advanceTimersByTime(120000);
    });
    expect(parseInt(fill.style.width, 10)).toBeLessThanOrEqual(95);
  });

  it('snaps to 100% on done and hides shortly after', () => {
    const { rerender } = render(<SummarizationProgress done={false} />);
    act(() => {
      jest.advanceTimersByTime(3000);
    });

    rerender(<SummarizationProgress done={true} />);
    expect(screen.getByTestId('summarization-progress-fill').style.width).toBe(
      '100%',
    );

    act(() => {
      jest.advanceTimersByTime(400);
    });
    expect(
      screen.queryByTestId('summarization-progress'),
    ).not.toBeInTheDocument();
  });
});
