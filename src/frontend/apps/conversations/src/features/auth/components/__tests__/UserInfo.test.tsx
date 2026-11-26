import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import fetchMock from 'fetch-mock';
import { PropsWithChildren } from 'react';
import { MemoryRouter } from 'react-router';

import { AppWrapper } from '@/tests/utils';

import { UserInfo } from '../UserInfo';

const API_BASE = 'http://test.jest/api/v1.0/';
const TERMS_URL = 'https://example.com/terms';

const CONFIG = {
  ENVIRONMENT: 'test',
  FEATURE_FLAGS: {},
  LANGUAGES: [['en-us', 'English']],
  LANGUAGE_CODE: 'en-us',
};

const USER = {
  id: 'user-1',
  email: 'jane@test.fr',
  full_name: 'Jane Doe',
  short_name: 'Jane',
};

const Wrapper = ({ children }: PropsWithChildren) => (
  <MemoryRouter>
    <AppWrapper>{children}</AppWrapper>
  </MemoryRouter>
);

const openUserMenu = async () => {
  render(<UserInfo />, { wrapper: Wrapper });
  await userEvent.click(
    await screen.findByRole('button', { name: 'Open user menu' }),
  );
};

describe('UserInfo', () => {
  beforeEach(() => {
    fetchMock.restore();
    localStorage.clear();
    fetchMock.get(`${API_BASE}users/me/`, { status: 200, body: USER });
  });

  it('links the terms of service from the theme customization', async () => {
    fetchMock.get(`${API_BASE}config/`, {
      status: 200,
      body: {
        ...CONFIG,
        theme_customization: { terms_of_service_url: TERMS_URL },
      },
    });

    await openUserMenu();

    expect(
      await screen.findByRole('link', { name: /Terms of Service/ }),
    ).toHaveAttribute('href', TERMS_URL);
  });

  it.each([
    ['missing', {}],
    ['empty', { terms_of_service_url: '' }],
  ])('hides the terms of service link when the URL is %s', async (_, theme) => {
    fetchMock.get(`${API_BASE}config/`, {
      status: 200,
      body: { ...CONFIG, theme_customization: theme },
    });

    await openUserMenu();

    expect(await screen.findByText('Logout')).toBeInTheDocument();
    expect(screen.queryByText('Terms of Service')).not.toBeInTheDocument();
  });
});
