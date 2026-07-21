import { renderHook, waitFor } from '@testing-library/react';
import fetchMock from 'fetch-mock';
import { Fragment } from 'react';

import { AbstractAnalytic } from '@/libs';
import { AppWrapper } from '@/tests/utils';

import { useAuth } from '../useAuth';

const trackEventMock = vi.fn();
const flag = true;
class TestAnalytic extends AbstractAnalytic {
  public constructor() {
    super();
  }

  public Provider() {
    return <Fragment />;
  }

  public trackEvent(props: any) {
    trackEventMock(props);
  }

  public isFeatureFlagActivated(flagName: string): boolean {
    if (flagName === 'CopyAsHTML') {
      return flag;
    }

    return true;
  }
}

vi.mock('react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useLocation: () => ({ pathname: '/dashboard' }),
}));

const dummyUser = { id: '123', email: 'test@example.com', sub: 'test-sub' };

describe('useAuth hook - trackEvent effect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.restore();
  });

  test('calls trackEvent when user exists, isSuccess is true, and event was not tracked yet', async () => {
    new TestAnalytic();

    fetchMock.get('http://test.jest/api/v1.0/users/me/', {
      body: JSON.stringify(dummyUser),
    });

    renderHook(() => useAuth(), {
      wrapper: AppWrapper,
    });

    await waitFor(() => {
      expect(trackEventMock).toHaveBeenCalledWith({
        eventName: 'user',
        id: dummyUser.id,
        email: dummyUser.email,
        sub: dummyUser.sub,
      });
    });
  });

  test('does not call trackEvent if already tracked', () => {
    fetchMock.get('http://test.jest/api/v1.0/users/me/', {
      body: JSON.stringify(dummyUser),
    });

    renderHook(() => useAuth(), {
      wrapper: AppWrapper,
    });

    expect(trackEventMock).not.toHaveBeenCalled();
  });
});
