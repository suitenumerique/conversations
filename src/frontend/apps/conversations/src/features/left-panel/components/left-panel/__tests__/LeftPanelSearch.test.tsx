import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { mockAllIsIntersecting } from 'react-intersection-observer/test-utils';
import { MemoryRouter } from 'react-router';

import { AppWrapper } from '@/tests/utils';

import { LeftPanelSearch } from '../LeftPanelSearch';

const fetchNextPage = vi.fn();

vi.mock('@/features/chat/api/useConversations', () => ({
  useInfiniteConversations: () => ({
    data: { pages: [{ results: [] }] },
    hasNextPage: true,
    fetchNextPage,
  }),
}));

describe('<LeftPanelSearch />', () => {
  beforeEach(() => {
    fetchNextPage.mockClear();
    // cmdk measures its list with a ResizeObserver, which jsdom lacks.
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('fetches the next page only when the loader scrolls into view', async () => {
    render(
      <AppWrapper>
        <MemoryRouter>
          <LeftPanelSearch />
        </MemoryRouter>
      </AppWrapper>,
    );

    await userEvent.type(screen.getByRole('combobox'), 'hello');
    expect(await screen.findByRole('group')).toBeInTheDocument();

    mockAllIsIntersecting(true);
    expect(fetchNextPage).toHaveBeenCalledTimes(1);

    mockAllIsIntersecting(false);
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });
});
