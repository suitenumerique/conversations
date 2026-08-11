import { fireEvent, render, screen } from '@testing-library/react';

import { AppWrapper } from '@/tests/utils';

import { StatusBanner } from '../StatusBanner';

const mockUseConfig = vi.fn();

vi.mock('@/core/config', () => ({
  useConfig: () => mockUseConfig(),
}));

describe('StatusBanner', () => {
  beforeEach(() => {
    mockUseConfig.mockReset();
  });

  it('renders nothing when no banner is configured', () => {
    mockUseConfig.mockReturnValue({ data: { status_banner: null } });
    render(<StatusBanner />, { wrapper: AppWrapper });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders title-only banner as a non-interactive status', () => {
    mockUseConfig.mockReturnValue({
      data: {
        status_banner: {
          type: 'status',
          level: 'info',
          title: 'Heads up',
          content: '',
        },
      },
    });

    render(<StatusBanner />, { wrapper: AppWrapper });

    expect(screen.getByText('Heads up')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders banner with content as a button and opens modal on click', () => {
    mockUseConfig.mockReturnValue({
      data: {
        status_banner: {
          type: 'status',
          level: 'warning',
          title: 'Ongoing technical issue',
          content: 'We are working on it.',
        },
      },
    });

    render(<StatusBanner />, { wrapper: AppWrapper });

    const trigger = screen.getByRole('button', {
      name: /show banner details/i,
    });
    expect(trigger).toBeInTheDocument();
    expect(screen.queryByText('We are working on it.')).not.toBeInTheDocument();

    fireEvent.click(trigger);

    expect(screen.getByText('We are working on it.')).toBeInTheDocument();
    expect(screen.getByText('What is happening?')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /i understand/i }),
    ).toBeInTheDocument();
  });

  it('closes the modal when the confirm button is clicked', () => {
    mockUseConfig.mockReturnValue({
      data: {
        status_banner: {
          type: 'status',
          level: 'alert',
          title: 'Outage',
          content: 'Details here.',
        },
      },
    });

    render(<StatusBanner />, { wrapper: AppWrapper });

    fireEvent.click(
      screen.getByRole('button', { name: /show banner details/i }),
    );
    expect(screen.getByText('Details here.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /i understand/i }));
    expect(screen.queryByText('Details here.')).not.toBeInTheDocument();
  });
});
