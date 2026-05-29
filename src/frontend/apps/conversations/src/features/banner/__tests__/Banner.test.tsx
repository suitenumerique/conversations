import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { Banner } from '../Banner';

describe('Banner', () => {
  it('renders as a non-interactive status region when content is empty', () => {
    render(<Banner level="info" title="System notice" content="" />, {
      wrapper: AppWrapper,
    });
    expect(screen.getByText('System notice')).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders as a button with info icon when content is non-empty', () => {
    render(
      <Banner level="warning" title="Slow response" content="Some details" />,
      { wrapper: AppWrapper },
    );
    expect(
      screen.getByRole('button', { name: /show banner details/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('opens modal on click when content is set', () => {
    render(
      <Banner level="alert" title="Unavailable" content="Full explanation" />,
      { wrapper: AppWrapper },
    );
    fireEvent.click(
      screen.getByRole('button', { name: /show banner details/i }),
    );
    expect(screen.getByText('Full explanation')).toBeInTheDocument();
    expect(screen.getByText('What is happening?')).toBeInTheDocument();
  });

  it('opens modal on Enter keydown', async () => {
    const user = userEvent.setup();
    render(<Banner level="warning" title="Slow response" content="Details" />, {
      wrapper: AppWrapper,
    });
    screen.getByRole('button', { name: /show banner details/i }).focus();
    await user.keyboard('{Enter}');
    expect(screen.getByText('Details')).toBeInTheDocument();
  });

  it('opens modal on Space keydown', async () => {
    const user = userEvent.setup();
    render(<Banner level="warning" title="Slow response" content="Details" />, {
      wrapper: AppWrapper,
    });
    screen.getByRole('button', { name: /show banner details/i }).focus();
    await user.keyboard(' ');
    expect(screen.getByText('Details')).toBeInTheDocument();
  });

  it('closes modal when the confirm button is clicked', () => {
    render(
      <Banner level="alert" title="Unavailable" content="Full explanation" />,
      { wrapper: AppWrapper },
    );
    fireEvent.click(
      screen.getByRole('button', { name: /show banner details/i }),
    );
    expect(screen.getByText('Full explanation')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /i understand/i }));
    expect(screen.queryByText('Full explanation')).not.toBeInTheDocument();
  });

  it('renders warning icon svg for warning level', () => {
    render(<Banner level="warning" title="Slow" content="" />, {
      wrapper: AppWrapper,
    });
    expect(screen.getByTestId('banner-icon')).toBeInTheDocument();
  });

  it('renders warning icon svg for alert level', () => {
    render(<Banner level="alert" title="Down" content="" />, {
      wrapper: AppWrapper,
    });
    expect(screen.getByTestId('banner-icon')).toBeInTheDocument();
  });

  it('renders no icon svg for info level', () => {
    render(<Banner level="info" title="Notice" content="" />, {
      wrapper: AppWrapper,
    });
    expect(screen.queryByTestId('banner-icon')).not.toBeInTheDocument();
  });
});
