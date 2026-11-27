import { act, renderHook } from '@testing-library/react';

import { useChatPreferencesStore } from '../../stores/useChatPreferencesStore';
import { useToggleForceConnector } from '../useToggleForceConnector';

const mockTrackEvent = vi.fn();
vi.mock('@/libs', () => ({
  useAnalytics: () => ({ trackEvent: mockTrackEvent }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  useChatPreferencesStore.setState({ forcedConnectors: [] });
});

const toggle = (slug: string) => {
  const { result } = renderHook(() => useToggleForceConnector());
  act(() => result.current(slug));
};

describe('useToggleForceConnector', () => {
  it('forces the connector and reports it', () => {
    toggle('sofia');

    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([
      'sofia',
    ]);
    expect(mockTrackEvent).toHaveBeenCalledWith({
      eventName: 'connector_force_toggled',
      properties: { connector_id: 'sofia', enabled: true },
    });
  });

  it('releases a forced connector and reports it', () => {
    useChatPreferencesStore.setState({ forcedConnectors: ['sofia'] });

    toggle('sofia');

    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([]);
    expect(mockTrackEvent).toHaveBeenCalledWith({
      eventName: 'connector_force_toggled',
      properties: { connector_id: 'sofia', enabled: false },
    });
  });
});
