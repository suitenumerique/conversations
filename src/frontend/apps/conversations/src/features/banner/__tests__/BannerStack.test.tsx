import { render, screen } from '@testing-library/react';

import { AppWrapper } from '@/tests/utils';

import { BannerStack } from '../BannerStack';

describe('BannerStack', () => {
  it('renders nothing when banners list is empty', () => {
    render(<BannerStack banners={[]} />, {
      wrapper: AppWrapper,
    });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders nothing when banners is undefined', () => {
    render(
      <BannerStack banners={undefined as any} />,
      { wrapper: AppWrapper },
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders one banner when one item is provided', () => {
    render(
      <BannerStack
        banners={[{ level: 'info', title: 'Hello', content: '' }]}
      />,
      { wrapper: AppWrapper },
    );
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders multiple banners stacked', () => {
    render(
      <BannerStack
        banners={[
          { level: 'warning', title: 'First', content: '' },
          { level: 'alert', title: 'Second', content: '' },
        ]}
      />,
      { wrapper: AppWrapper },
    );
    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });
});
