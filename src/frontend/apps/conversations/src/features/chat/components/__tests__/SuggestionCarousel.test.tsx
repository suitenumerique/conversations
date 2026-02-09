import { render, screen } from '@testing-library/react';
import i18next from 'i18next';

import '@/i18n/initI18n';

import { SuggestionCarousel } from '../SuggestionCarousel';

describe('SuggestionCarousel', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(async () => {
    jest.useRealTimers();
    await i18next.changeLanguage('en');
  });

  it('should render all suggestions in french', async () => {
    await i18next.changeLanguage('fr');

    render(<SuggestionCarousel messagesLength={0} />);

    expect(screen.getAllByText('Poser une question')).toHaveLength(2);
    expect(
      screen.getByText('Transformer cette liste en liste à puces...'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Écrire une description courte du produit...'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Trouver les dernières actualités concernant...'),
    ).toBeInTheDocument();
  });

  it('should render all suggestions', () => {
    render(<SuggestionCarousel messagesLength={0} />);

    // First suggestion appears twice (duplicated for looping animation)
    expect(screen.getAllByText('Ask a question')).toHaveLength(2);
    expect(
      screen.getByText('Turn this list into bullet points'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Write a short product description'),
    ).toBeInTheDocument();
    expect(screen.getByText('Find recent news about...')).toBeInTheDocument();
  });

  it('should start the interval when messagesLength is 0', () => {
    const setIntervalSpy = jest.spyOn(global, 'setInterval');

    render(<SuggestionCarousel messagesLength={0} />);

    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 3000);

    setIntervalSpy.mockRestore();
  });

  it('should not start interval when messagesLength is greater than 0', () => {
    const setIntervalSpy = jest.spyOn(global, 'setInterval');

    render(<SuggestionCarousel messagesLength={1} />);

    expect(setIntervalSpy).not.toHaveBeenCalled();

    setIntervalSpy.mockRestore();
  });

  it('should clear interval on unmount', () => {
    const clearIntervalSpy = jest.spyOn(global, 'clearInterval');

    const { unmount } = render(<SuggestionCarousel messagesLength={0} />);
    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();

    clearIntervalSpy.mockRestore();
  });
});
