import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import fetchMock from 'fetch-mock';

import { useToast } from '@/components';
import { ChatProject } from '@/features/chat/types';

import { ModalProjectForm } from '../ModalProjectForm';

jest.mock('@/components', () => ({
  ...jest.requireActual('@/components'),
  useToast: jest.fn(),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));
jest.mock('i18next', () => ({
  t: (key: string) => key,
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

describe('ModalProjectForm', () => {
  const mockOnClose = jest.fn();
  const mockShowToast = jest.fn();

  const existingProject: ChatProject = {
    id: 'proj-123',
    title: 'My Project',
    icon: 'star',
    color: 'color_3',
    llm_instructions: 'Be helpful',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    conversations: [],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    fetchMock.restore();
    (useToast as jest.Mock).mockReturnValue({
      showToast: mockShowToast,
    });
  });

  it('submits correct payload in create mode', async () => {
    const user = userEvent.setup();
    fetchMock.post(`${API_BASE}projects/`, {
      status: 201,
      body: {
        id: 'new-id',
        title: 'Test',
        icon: 'folder',
        color: 'color_6',
        llm_instructions: '',
        created_at: '',
        updated_at: '',
        conversations: [],
      },
    });

    renderWithProviders(<ModalProjectForm onClose={mockOnClose} />);

    await user.type(
      screen.getByRole('textbox', { name: 'Project name' }),
      'Test',
    );
    await user.click(screen.getByRole('button', { name: 'Create project' }));

    await waitFor(() => expect(fetchMock.called()).toBe(true));

    const [, options] = fetchMock.lastCall()!;
    const body = JSON.parse(options!.body as string) as Record<string, unknown>;
    expect(body).toEqual({
      title: 'Test',
      icon: 'folder',
      color: 'color_6',
    });
  });

  it('submits correct payload in edit mode', async () => {
    const user = userEvent.setup();
    fetchMock.patch(`${API_BASE}projects/proj-123/`, 200);

    renderWithProviders(
      <ModalProjectForm onClose={mockOnClose} project={existingProject} />,
    );

    const input = screen.getByRole('textbox', { name: 'Project name' });
    await user.clear(input);
    await user.type(input, 'Updated');
    await user.click(
      screen.getByRole('button', { name: 'Save project settings' }),
    );

    await waitFor(() => expect(fetchMock.called()).toBe(true));

    const [url, options] = fetchMock.lastCall()!;
    expect(url).toContain('projects/proj-123/');
    const body = JSON.parse(options!.body as string) as Record<string, unknown>;
    expect(body).toEqual({
      title: 'Updated',
      icon: 'star',
      color: 'color_3',
      llm_instructions: 'Be helpful',
    });
  });

  it('disables submit button when name is empty or whitespace', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ModalProjectForm onClose={mockOnClose} />);

    const submitButton = screen.getByRole('button', { name: 'Create project' });

    // Initially disabled (empty name)
    expect(submitButton).toBeDisabled();

    // Type whitespace only - still disabled
    await user.type(
      screen.getByRole('textbox', { name: 'Project name' }),
      '   ',
    );
    expect(submitButton).toBeDisabled();
  });

  it('shows success toast and closes modal on create', async () => {
    const user = userEvent.setup();
    fetchMock.post(`${API_BASE}projects/`, {
      status: 201,
      body: {
        id: 'new-id',
        title: 'Test',
        icon: 'folder',
        color: 'color_6',
        llm_instructions: '',
        created_at: '',
        updated_at: '',
        conversations: [],
      },
    });

    renderWithProviders(<ModalProjectForm onClose={mockOnClose} />);

    await user.type(
      screen.getByRole('textbox', { name: 'Project name' }),
      'Test',
    );
    await user.click(screen.getByRole('button', { name: 'Create project' }));

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        'success',
        'The project has been created.',
        undefined,
        4000,
      );
    });
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('shows API error message on failed create', async () => {
    const user = userEvent.setup();
    fetchMock.post(`${API_BASE}projects/`, {
      status: 400,
      body: { title: ['A project with this title already exists.'] },
    });

    renderWithProviders(<ModalProjectForm onClose={mockOnClose} />);

    await user.type(
      screen.getByRole('textbox', { name: 'Project name' }),
      'Duplicate',
    );
    await user.click(screen.getByRole('button', { name: 'Create project' }));

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        'error',
        'A project with this title already exists.',
        undefined,
        4000,
      );
    });
    expect(mockOnClose).not.toHaveBeenCalled();
  });
});
