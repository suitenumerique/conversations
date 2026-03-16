import { CunninghamProvider } from '@gouvfr-lasuite/cunningham-react';
import { render, screen } from '@testing-library/react';

import { ChatConversation } from '@/features/chat/types';

import { QuickSearchResultItem } from '../QuickSearchResultItem';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));
jest.mock('i18next', () => ({
  t: (key: string) => key,
}));

const renderWithProviders = (component: React.ReactNode) =>
  render(<CunninghamProvider>{component}</CunninghamProvider>);

const makeConversation = (
  overrides?: Partial<ChatConversation>,
): ChatConversation => ({
  id: 'conv-1',
  title: 'Test conversation',
  messages: [],
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-05T00:00:00Z',
  ...overrides,
});

describe('QuickSearchResultItem', () => {
  it('renders conversation title and relative date when conversation has a project', () => {
    const conversation = makeConversation({
      project: 'proj-1',
    });

    renderWithProviders(<QuickSearchResultItem conversation={conversation} />);

    expect(screen.getByText('Test conversation')).toBeInTheDocument();
  });

  it('renders relative date when conversation has no project', () => {
    const conversation = makeConversation({ project: null });

    renderWithProviders(<QuickSearchResultItem conversation={conversation} />);

    expect(screen.getByText('Test conversation')).toBeInTheDocument();
    expect(screen.queryByText('\u2022')).not.toBeInTheDocument();
  });

  it('shows "Untitled conversation" when title is empty', () => {
    const conversation = makeConversation({ title: '' });

    renderWithProviders(<QuickSearchResultItem conversation={conversation} />);

    expect(screen.getByText('Untitled conversation')).toBeInTheDocument();
  });
});
