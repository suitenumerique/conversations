import { render, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { ConnectorLinkReturn } from '../ConnectorLinkReturn';

const mockShowToast = vi.fn();
vi.mock('@/components/ToastProvider', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

vi.mock('@/core', () => ({
  useConfig: () => ({
    data: {
      CONNECTORS: [
        {
          slug: 'sofia',
          name: 'SofIA',
          feature_flag: null,
          auth: 'user_oauth',
        },
      ],
    },
  }),
}));

let currentSearch = '';
const LocationProbe = () => {
  currentSearch = useLocation().search;
  return null;
};

const renderAt = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <AppWrapper>
        <ConnectorLinkReturn />
        <LocationProbe />
      </AppWrapper>
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  currentSearch = '';
});

describe('ConnectorLinkReturn', () => {
  it('confirms a linked connector and cleans the URL', async () => {
    renderAt('/?connector=sofia&connector_status=linked&keep=1');

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'success',
        'SofIA is connected.',
        undefined,
        5000,
      ),
    );
    await waitFor(() => expect(currentSearch).toBe('?keep=1'));
  });

  it('reports a failed authorization', async () => {
    renderAt('/?connector=sofia&connector_status=error');

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'error',
        'SofIA could not be connected.',
        'error',
        5000,
      ),
    );
  });

  it('does nothing on an ordinary page load', () => {
    renderAt('/chat');
    expect(mockShowToast).not.toHaveBeenCalled();
  });
});
