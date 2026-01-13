import { render, screen } from '@testing-library/react';

import '@/i18n/initI18n';

import { WelcomeMessage } from '../WelcomeMessage';

describe('WelcomeMessage', () => {
  it('should render the welcome message', () => {
    render(<WelcomeMessage />);

    expect(
      screen.getByRole('heading', { level: 2, name: 'What is on your mind?' }),
    ).toBeInTheDocument();
  });
});
