import { renderHook, waitFor } from '@testing-library/react';
import fetchMock from 'fetch-mock';

import { useConfig } from '@/core/config';
import { AppWrapper } from '@/tests/utils';

import packageJson from '../../../../package.json';
import { useNewVersionBanner } from '../useNewVersionBanner';

const API_BASE = 'http://test.jest/api/v1.0/';
// Kept private by the config module, repeated here to seed the stored copy.
const LOCAL_STORAGE_KEY = 'conversations_config';

const CONFIG = {
  ENVIRONMENT: 'test',
  FEATURE_FLAGS: {},
  LANGUAGES: [['en-us', 'English']],
  LANGUAGE_CODE: 'en-us',
};

const getBannerOnceFetched = async () => {
  const { result } = renderHook(
    () => ({ banner: useNewVersionBanner(), config: useConfig() }),
    { wrapper: AppWrapper },
  );
  await waitFor(() => expect(result.current.config.isFetched).toBe(true));
  return result.current.banner;
};

describe('useNewVersionBanner', () => {
  beforeEach(() => {
    fetchMock.restore();
  });

  // Must run first: the config module reads the stored copy only once.
  it('ignores the release of the config stored by a previous visit', async () => {
    localStorage.setItem(
      LOCAL_STORAGE_KEY,
      JSON.stringify({ ...CONFIG, RELEASE: '0.0.1' }),
    );
    fetchMock.get(`${API_BASE}config/`, {
      status: 200,
      body: { ...CONFIG, RELEASE: packageJson.version },
    });

    const { result } = renderHook(() => useNewVersionBanner(), {
      wrapper: AppWrapper,
    });
    expect(result.current).toBeUndefined();

    await waitFor(() => expect(fetchMock.called()).toBe(true));
    expect(result.current).toBeUndefined();
  });

  it('shows a reload banner when the backend runs another release', async () => {
    fetchMock.get(`${API_BASE}config/`, {
      status: 200,
      body: { ...CONFIG, RELEASE: '999.0.0' },
    });

    const banner = await getBannerOnceFetched();

    expect(banner).toMatchObject({
      level: 'warning',
      action: { label: 'Reload' },
    });
  });

  it('shows nothing when the backend runs the same release', async () => {
    fetchMock.get(`${API_BASE}config/`, {
      status: 200,
      body: { ...CONFIG, RELEASE: packageJson.version },
    });

    const banner = await getBannerOnceFetched();

    expect(banner).toBeUndefined();
  });

  it('shows nothing when the backend does not report its release', async () => {
    fetchMock.get(`${API_BASE}config/`, { status: 200, body: CONFIG });

    const banner = await getBannerOnceFetched();

    expect(banner).toBeUndefined();
  });
});
