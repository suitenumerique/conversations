import { render, screen } from '@testing-library/react';

import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

import { ArenaIntro } from '../ArenaIntro';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const INTRO =
  'Two answers are shown. Choose the one you prefer, it will be kept in the conversation.';

describe('ArenaIntro', () => {
  beforeEach(() => {
    useChatPreferencesStore.setState({ hasSeenArenaIntro: false });
  });

  it('shows the sentence the first time and marks it as seen', () => {
    render(<ArenaIntro />);

    expect(screen.getByText(INTRO)).toBeInTheDocument();
    expect(useChatPreferencesStore.getState().hasSeenArenaIntro).toBe(true);
  });

  it('keeps the sentence on screen for the split it was mounted with', () => {
    const { rerender } = render(<ArenaIntro />);
    rerender(<ArenaIntro />);

    expect(screen.getByText(INTRO)).toBeInTheDocument();
  });

  it('renders nothing once the intro has been seen', () => {
    useChatPreferencesStore.setState({ hasSeenArenaIntro: true });

    const { container } = render(<ArenaIntro />);

    expect(container).toBeEmptyDOMElement();
  });
});
