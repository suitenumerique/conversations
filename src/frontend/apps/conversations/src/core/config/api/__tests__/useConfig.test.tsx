import { renderHook, waitFor } from '@testing-library/react';
import fetchMock from 'fetch-mock';

import { AppWrapper } from '@/tests/utils';

import { useConfig } from '../useConfig';

const API_BASE = 'http://test.jest/api/v1.0/';
// Kept private by the hook module, repeated here so the test can watch reads.
const LOCAL_STORAGE_KEY = 'conversations_config';

const CACHED_CONFIG = {
  ACTIVATION_REQUIRED: false,
  ENVIRONMENT: 'test',
  FEATURE_FLAGS: {},
  LANGUAGES: [['en-us', 'English']],
  LANGUAGE_CODE: 'en-us',
};

describe('useConfig', () => {
  beforeEach(() => {
    fetchMock.restore();
  });

  // The config is read by ~19 call sites, several of which render continuously
  // while a response streams. Reading and parsing it per render put a
  // synchronous localStorage hit and a JSON parse of the whole payload on the
  // main thread every time; it only ever seeds the query cache.
  it('reads the cached config from storage once, not on every render', async () => {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(CACHED_CONFIG));
    fetchMock.get(`${API_BASE}config/`, { status: 200, body: CACHED_CONFIG });

    const getItem = jest.spyOn(Storage.prototype, 'getItem');

    // Several consumers per render, as in the real component tree.
    const { result, rerender } = renderHook(
      () => [useConfig(), useConfig(), useConfig()],
      { wrapper: AppWrapper },
    );

    await waitFor(() => expect(result.current[0].isFetching).toBe(false));

    rerender();
    rerender();
    rerender();

    const configReads = getItem.mock.calls.filter(
      ([key]) => key === LOCAL_STORAGE_KEY,
    );
    expect(configReads).toHaveLength(1);

    // The cached payload still seeds the query, so consumers keep rendering
    // against it instead of waiting for the request.
    expect(result.current[0].data!.LANGUAGE_CODE).toBe('en-us');

    getItem.mockRestore();
  });
});
