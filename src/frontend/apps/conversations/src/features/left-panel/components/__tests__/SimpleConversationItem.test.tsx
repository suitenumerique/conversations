import { render, screen } from '@testing-library/react';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { SimpleConversationItem } from '../SimpleConversationItem';

jest.mock('../../assets/bubble-bold.svg', () => {
  return function BubbleIcon({ color, ...props }: { color: string }) {
    return <svg data-testid="bubble-icon" data-color={color} {...props} />;
  };
});

const mockConversation = {
  id: 'conv-123',
  title: 'Test Conversation',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  messages: [],
};

const renderWithWrapper = (ui: React.ReactElement) => {
  return render(ui, { wrapper: AppWrapper });
};

describe('SimpleConversationItem', () => {
  it('should render conversation title', () => {
    renderWithWrapper(
      <SimpleConversationItem conversation={mockConversation} />,
    );

    expect(screen.getByText('Test Conversation')).toBeInTheDocument();
  });

  it('should render bubble icon', () => {
    renderWithWrapper(
      <SimpleConversationItem conversation={mockConversation} />,
    );

    expect(screen.getByTestId('bubble-icon')).toBeInTheDocument();
  });

  it('should have accessible label for bubble icon', () => {
    renderWithWrapper(
      <SimpleConversationItem conversation={mockConversation} />,
    );

    expect(screen.getByLabelText('Simple chat icon')).toBeInTheDocument();
  });

  it('should display "Untitled conversation" when title is empty', () => {
    renderWithWrapper(
      <SimpleConversationItem
        conversation={{ ...mockConversation, title: '' }}
      />,
    );

    expect(screen.getByText('Untitled conversation')).toBeInTheDocument();
  });

  it('should display "Untitled conversation" when title is undefined', () => {
    renderWithWrapper(
      <SimpleConversationItem
        conversation={{
          ...mockConversation,
          title: undefined as unknown as string,
        }}
      />,
    );

    expect(screen.getByText('Untitled conversation')).toBeInTheDocument();
  });

  it('should have aria-label with the title', () => {
    renderWithWrapper(
      <SimpleConversationItem conversation={mockConversation} />,
    );

    expect(screen.getByLabelText('Test Conversation')).toBeInTheDocument();
  });

  it('should have aria-label with "Untitled conversation" when title is empty', () => {
    renderWithWrapper(
      <SimpleConversationItem
        conversation={{ ...mockConversation, title: '' }}
      />,
    );

    expect(screen.getByLabelText('Untitled conversation')).toBeInTheDocument();
  });
});
