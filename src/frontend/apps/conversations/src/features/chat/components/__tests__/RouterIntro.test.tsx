import { render, screen } from '@testing-library/react';

import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

import { RouterIntro } from '../RouterIntro';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const INTRO =
  'For each question, the assistant automatically picks the most suitable and most frugal model. You can see this choice under each answer.';

describe('RouterIntro', () => {
  beforeEach(() => {
    useChatPreferencesStore.setState({ hasSeenRouterIntro: false });
  });

  it('shows the sentence the first time and marks it as seen', () => {
    render(<RouterIntro />);

    expect(screen.getByText(INTRO)).toBeInTheDocument();
    expect(useChatPreferencesStore.getState().hasSeenRouterIntro).toBe(true);
  });

  it('keeps the sentence on screen for the answer it was mounted with', () => {
    const { rerender } = render(<RouterIntro />);
    rerender(<RouterIntro />);

    expect(screen.getByText(INTRO)).toBeInTheDocument();
  });

  it('renders nothing once the intro has been seen', () => {
    useChatPreferencesStore.setState({ hasSeenRouterIntro: true });

    const { container } = render(<RouterIntro />);

    expect(container).toBeEmptyDOMElement();
  });
});
