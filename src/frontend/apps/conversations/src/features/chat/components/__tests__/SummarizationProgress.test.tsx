import { act, render, screen } from '@testing-library/react';

import { SummarizationProgress } from '../SummarizationProgress';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('SummarizationProgress', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
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
      vi.advanceTimersByTime(30000); // one time constant
    });
    const fill = screen.getByTestId('summarization-progress-fill');
    const afterOneTau = parseInt(fill.style.width, 10);
    expect(afterOneTau).toBeGreaterThan(50); // ~60% at t = τ
    expect(afterOneTau).toBeLessThan(95);

    act(() => {
      vi.advanceTimersByTime(120000);
    });
    expect(parseInt(fill.style.width, 10)).toBeLessThanOrEqual(95);
  });

  it('snaps to 100% on done and hides shortly after', () => {
    const { rerender } = render(<SummarizationProgress done={false} />);
    act(() => {
      vi.advanceTimersByTime(3000);
    });

    rerender(<SummarizationProgress done={true} />);
    expect(screen.getByTestId('summarization-progress-fill').style.width).toBe(
      '100%',
    );

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(
      screen.queryByTestId('summarization-progress'),
    ).not.toBeInTheDocument();
  });

  it('calls onHidden once the bar has hidden itself', () => {
    const onHidden = vi.fn();
    const { rerender } = render(
      <SummarizationProgress done={false} onHidden={onHidden} />,
    );

    rerender(<SummarizationProgress done={true} onHidden={onHidden} />);
    expect(onHidden).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(onHidden).toHaveBeenCalledTimes(1);
  });
});
