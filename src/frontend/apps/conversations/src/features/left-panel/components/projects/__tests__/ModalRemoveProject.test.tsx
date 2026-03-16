import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import fetchMock from 'fetch-mock';

import { useToast } from '@/components';

import { ModalRemoveProject } from '../ModalRemoveProject';

jest.mock('@/components', () => ({
  ...jest.requireActual('@/components'),
  useToast: jest.fn(),
}));

const mockPush = jest.fn();
jest.mock('next/router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

let mockPathname = '/';
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string>) => {
      if (options) {
        return Object.entries(options).reduce(
          (acc, [k, v]) => acc.replace(`{{${k}}}`, v),
          key,
        );
      }
      return key;
    },
  }),
}));
jest.mock('i18next', () => ({
  t: (key: string, options?: Record<string, string>) => {
    if (options) {
      return Object.entries(options).reduce(
        (acc, [k, v]) => acc.replace(`{{${k}}}`, v),
        key,
      );
    }
    return key;
  },
}));

const API_BASE = 'http://test.jest/api/v1.0/';

const renderWithProviders = (component: React.ReactNode) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CunninghamProvider>{component}</CunninghamProvider>
    </QueryClientProvider>,
  );
};

describe('ModalRemoveProject', () => {
  const mockOnClose = jest.fn();
  const mockShowToast = jest.fn();
  const project = { id: 'proj-123', title: 'My Project' };

  beforeEach(() => {
    jest.clearAllMocks();
    fetchMock.restore();
    mockPathname = '/';
    (useToast as jest.Mock).mockReturnValue({
      showToast: mockShowToast,
    });
  });

  it('sends DELETE request on confirm button click', async () => {
    const user = userEvent.setup();
    fetchMock.delete(`${API_BASE}projects/proj-123/`, 204);

    renderWithProviders(
      <ModalRemoveProject onClose={mockOnClose} project={project} />,
    );

    await user.click(screen.getByRole('button', { name: 'Confirm deletion' }));

    await waitFor(() => expect(fetchMock.called()).toBe(true));

    const [url, options] = fetchMock.lastCall()!;
    expect(url).toContain('projects/proj-123/');
    expect(options!.method).toBe('DELETE');
  });

  it('shows success toast and navigates home on success when not on home', async () => {
    const user = userEvent.setup();
    mockPathname = '/chat/some-id';
    fetchMock.delete(`${API_BASE}projects/proj-123/`, 204);

    renderWithProviders(
      <ModalRemoveProject onClose={mockOnClose} project={project} />,
    );

    await user.click(screen.getByRole('button', { name: 'Confirm deletion' }));

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        'success',
        'The project has been deleted.',
        undefined,
        4000,
      );
    });
    expect(mockPush).toHaveBeenCalledWith('/');
    expect(mockOnClose).not.toHaveBeenCalled();
  });

  it('shows success toast and closes modal when already on home', async () => {
    const user = userEvent.setup();
    mockPathname = '/';
    fetchMock.delete(`${API_BASE}projects/proj-123/`, 204);

    renderWithProviders(
      <ModalRemoveProject onClose={mockOnClose} project={project} />,
    );

    await user.click(screen.getByRole('button', { name: 'Confirm deletion' }));

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        'success',
        'The project has been deleted.',
        undefined,
        4000,
      );
    });
    expect(mockOnClose).toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
