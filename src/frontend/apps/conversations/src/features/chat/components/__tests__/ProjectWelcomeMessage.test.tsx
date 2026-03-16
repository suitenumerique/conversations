import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import {
  InfiniteData,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';

import {
  KEY_LIST_PROJECT,
  ProjectsResponse,
} from '@/features/chat/api/useProjects';
import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';
import { ChatProject } from '@/features/chat/types';

import { ProjectWelcomeMessage } from '../ProjectWelcomeMessage';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));
jest.mock('i18next', () => ({
  t: (key: string) => key,
}));

const makeProject = (overrides?: Partial<ChatProject>): ChatProject => ({
  id: 'proj-1',
  title: 'Design System',
  icon: 'folder',
  color: 'color_6',
  llm_instructions: '',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  conversations: [],
  ...overrides,
});

const renderWithCache = (
  projectId: string | null,
  cachedProjects: ChatProject[],
) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  if (cachedProjects.length > 0) {
    const cacheData: InfiniteData<ProjectsResponse> = {
      pages: [
        {
          count: cachedProjects.length,
          results: cachedProjects,
          next: null,
          previous: null,
        },
      ],
      pageParams: [1],
    };
    queryClient.setQueryData([KEY_LIST_PROJECT, { page: 1 }], cacheData);
  }

  usePendingChatStore.setState({ projectId });

  return render(
    <QueryClientProvider client={queryClient}>
      <CunninghamProvider>
        <ProjectWelcomeMessage fallback={<span>Welcome fallback</span>} />
      </CunninghamProvider>
    </QueryClientProvider>,
  );
};

describe('ProjectWelcomeMessage', () => {
  beforeEach(() => {
    usePendingChatStore.setState({
      projectId: null,
      input: '',
      files: null,
    });
  });

  it('renders project title when projectId matches a cached project', () => {
    renderWithCache('proj-1', [makeProject()]);

    expect(screen.getByText('Design System')).toBeInTheDocument();
    expect(screen.queryByText('Welcome fallback')).not.toBeInTheDocument();
  });

  it('renders fallback when no project found in cache', () => {
    renderWithCache('proj-unknown', [makeProject()]);

    expect(screen.getByText('Welcome fallback')).toBeInTheDocument();
    expect(screen.queryByText('Design System')).not.toBeInTheDocument();
  });

  it('renders fallback when projectId is null', () => {
    renderWithCache(null, [makeProject()]);

    expect(screen.getByText('Welcome fallback')).toBeInTheDocument();
  });
});
