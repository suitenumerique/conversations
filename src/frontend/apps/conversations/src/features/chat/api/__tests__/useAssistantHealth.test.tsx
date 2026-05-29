import { act, renderHook, waitFor } from '@testing-library/react';
import fetchMock from 'fetch-mock';

import { AppWrapper } from '@/tests/utils';

import { useAssistantHealth } from '../useAssistantHealth';

const API_BASE = 'http://test.jest/api/v1.0/';

describe('useAssistantHealth', () => {
  beforeEach(() => {
    fetchMock.restore();
  });

  it('returns banners and blocked=false on success', async () => {
    fetchMock.get(`${API_BASE}assistant-health/`, {
      status: 200,
      body: {
        banners: [
          {
            level: 'warning',
            title: "L'assistant répond lentement",
            content: '',
          },
        ],
        blocked: false,
      },
    });

    const { result } = renderHook(() => useAssistantHealth(), {
      wrapper: AppWrapper,
    });

    await waitFor(() => expect(result.current.data).toBeDefined());

    expect(result.current.data!.banners).toHaveLength(1);
    expect(result.current.data!.banners[0].level).toBe('warning');
    expect(result.current.data!.blocked).toBe(false);
  });

  it('returns empty banners and blocked=false on API error', async () => {
    fetchMock.get(`${API_BASE}assistant-health/`, { status: 500 });

    const { result } = renderHook(() => useAssistantHealth(), {
      wrapper: AppWrapper,
    });

    await waitFor(() => expect(result.current.data).toBeDefined());

    // fail-open: queryFn catches the error and returns FALLBACK
    expect(result.current.data).toEqual({ banners: [], blocked: false });
  });

  it('returns empty banners and blocked=false on malformed JSON', async () => {
    fetchMock.get(`${API_BASE}assistant-health/`, {
      status: 200,
      body: 'not-json',
      headers: { 'Content-Type': 'text/plain' },
    });

    const { result } = renderHook(() => useAssistantHealth(), {
      wrapper: AppWrapper,
    });

    await waitFor(() => expect(result.current.data).toBeDefined());

    // fail-open: JSON parse error is caught and falls back to FALLBACK
    expect(result.current.data).toEqual({ banners: [], blocked: false });
  });

  it('returns blocked=true when API signals blocked', async () => {
    fetchMock.get(`${API_BASE}assistant-health/`, {
      status: 200,
      body: {
        banners: [
          { level: 'alert', title: 'Assistant indisponible', content: '' },
        ],
        blocked: true,
      },
    });

    const { result } = renderHook(() => useAssistantHealth(), {
      wrapper: AppWrapper,
    });

    await waitFor(() => expect(result.current.data).toBeDefined());

    expect(result.current.data!.blocked).toBe(true);
  });

  it('polls the endpoint every 60 seconds', async () => {
    jest.useFakeTimers();

    fetchMock.get(`${API_BASE}assistant-health/`, {
      status: 200,
      body: { banners: [], blocked: false },
    });

    const { result } = renderHook(() => useAssistantHealth(), {
      wrapper: AppWrapper,
    });

    await act(async () => {
      await Promise.resolve();
    });
    await waitFor(() => expect(result.current.data).toBeDefined());

    const callsBefore = fetchMock.calls().length;
    expect(callsBefore).toBeGreaterThanOrEqual(1);

    await act(async () => {
      jest.advanceTimersByTime(60_000);
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(fetchMock.calls().length).toBeGreaterThan(callsBefore),
    );

    jest.useRealTimers();
  });
});
