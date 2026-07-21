import { render, screen } from '@testing-library/react';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { MainLayout } from '../MainLayout';

vi.mock('@/stores', () => ({
  useResponsiveStore: () => ({ isDesktop: true, isMobile: false }),
}));

vi.mock('@/features/chat/stores/useChatPreferencesStore', () => ({
  useChatPreferencesStore: () => ({ isPanelOpen: false }),
}));

const mockUseConfig = vi.fn();
vi.mock('@/core/config', () => ({
  useConfig: () => mockUseConfig(),
}));

const mockUseAssistantHealth = vi.fn();
vi.mock('@/features/chat/api/useAssistantHealth', () => ({
  useAssistantHealth: () => mockUseAssistantHealth(),
}));

vi.mock('@/features/header', () => ({
  Header: () => <div data-testid="header" />,
}));

vi.mock('@/features/left-panel', () => ({
  LeftPanel: () => <div data-testid="left-panel" />,
}));

vi.mock('@/features/banner', () => ({
  BannerStack: ({ banners }: { banners: { title: string }[] }) => (
    <div data-testid="banner-stack">
      {(banners ?? []).map((b, i) => (
        <div key={i} data-testid={`banner-item-${i}`}>
          {b.title}
        </div>
      ))}
    </div>
  ),
}));

describe('MainLayout', () => {
  beforeEach(() => {
    mockUseConfig.mockReturnValue({ data: { status_banner: null } });
    mockUseAssistantHealth.mockReturnValue({
      data: { banners: [], blocked: false },
    });
  });

  it('renders both config and health banners when both sources provide them', () => {
    mockUseConfig.mockReturnValue({
      data: {
        status_banner: { level: 'info', title: 'Admin notice', content: '' },
      },
    });
    mockUseAssistantHealth.mockReturnValue({
      data: {
        banners: [{ level: 'warning', title: 'Health warning', content: '' }],
        blocked: false,
      },
    });

    render(<MainLayout />, { wrapper: AppWrapper });

    const items = screen.getAllByTestId(/^banner-item-/);
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Admin notice');
    expect(items[1]).toHaveTextContent('Health warning');
  });

  it('renders only health banner when config banner is absent', () => {
    mockUseAssistantHealth.mockReturnValue({
      data: {
        banners: [{ level: 'alert', title: 'Model down', content: '' }],
        blocked: true,
      },
    });

    render(<MainLayout />, { wrapper: AppWrapper });

    expect(screen.getByText('Model down')).toBeInTheDocument();
    expect(screen.getAllByTestId(/^banner-item-/)).toHaveLength(1);
  });

  it('renders no banners when both sources are empty', () => {
    render(<MainLayout />, { wrapper: AppWrapper });

    expect(screen.queryByTestId('banner-item-0')).not.toBeInTheDocument();
  });
});
