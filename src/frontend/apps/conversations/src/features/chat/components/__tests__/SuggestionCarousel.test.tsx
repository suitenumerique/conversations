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
      screen.getByText('Transformer cette liste en points à puces'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Écrire une description courte du produit'),
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

  it('should show banner title when blocked and not show carousel suggestions', () => {
    render(
      <SuggestionCarousel
        messagesLength={0}
        blocked={true}
        banners={[
          { level: 'alert', title: 'Service unavailable', content: '' },
        ]}
      />,
    );

    expect(screen.getAllByText('Service unavailable').length).toBeGreaterThan(
      0,
    );
    expect(screen.queryByText('Ask a question')).not.toBeInTheDocument();
  });

  it('should carousel through title and content when blocked and banner has content', () => {
    render(
      <SuggestionCarousel
        messagesLength={0}
        blocked={true}
        banners={[
          {
            level: 'alert',
            title: 'Service unavailable',
            content: 'Maintenance in progress',
          },
        ]}
      />,
    );

    // Both items are rendered in the carousel DOM (one visible at a time via CSS transform)
    expect(screen.getAllByText('Service unavailable').length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText('Maintenance in progress')).toBeInTheDocument();
  });

  it('should render empty wrapper without crashing when blocked with no banners', () => {
    render(
      <SuggestionCarousel messagesLength={0} blocked={true} banners={[]} />,
    );

    expect(screen.queryByText('Ask a question')).not.toBeInTheDocument();
  });

  it('should show carousel suggestions when not blocked', () => {
    render(
      <SuggestionCarousel
        messagesLength={0}
        blocked={false}
        banners={[
          { level: 'alert', title: 'Service unavailable', content: '' },
        ]}
      />,
    );

    expect(screen.getAllByText('Ask a question')).toHaveLength(2);
    expect(screen.queryByText('Service unavailable')).not.toBeInTheDocument();
  });
});
