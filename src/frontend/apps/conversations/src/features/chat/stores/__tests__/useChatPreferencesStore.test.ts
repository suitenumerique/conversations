import { useChatPreferencesStore } from '../useChatPreferencesStore';

const STORAGE_KEY = 'chat-preferences';

beforeEach(() => {
  useChatPreferencesStore.setState({
    forceWebSearch: false,
    forcedConnectors: [],
  });
});

describe('useChatPreferencesStore', () => {
  it('starts with no connector forced', () => {
    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([]);
  });

  it('toggles each connector force independently of web search', () => {
    const { toggleForceConnector } = useChatPreferencesStore.getState();

    toggleForceConnector('sofia');
    toggleForceConnector('datagouv');
    toggleForceConnector('sofia');

    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([
      'datagouv',
    ]);
    expect(useChatPreferencesStore.getState().forceWebSearch).toBe(false);
  });

  it('remembers the forces in localStorage, and nothing else about them', () => {
    useChatPreferencesStore.getState().toggleForceConnector('sofia');

    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as {
      state: Record<string, unknown>;
    };
    expect(stored.state.forcedConnectors).toEqual(['sofia']);
    expect(stored.state).not.toHaveProperty('forceDatagouv');
  });

  it('carries a data.gouv force saved by an older version over as its slug', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        state: { forceWebSearch: true, forceDatagouv: true },
        version: 0,
      }),
    );

    await useChatPreferencesStore.persist.rehydrate();

    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([
      'datagouv',
    ]);
    expect(useChatPreferencesStore.getState().forceWebSearch).toBe(true);
    expect(useChatPreferencesStore.getState()).not.toHaveProperty(
      'forceDatagouv',
    );
  });

  it('migrates an older version without a data.gouv force to no force', async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ state: { forceDatagouv: false }, version: 0 }),
    );

    await useChatPreferencesStore.persist.rehydrate();

    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([]);
  });
});
