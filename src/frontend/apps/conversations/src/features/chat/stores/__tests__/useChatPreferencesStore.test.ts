import { useChatPreferencesStore } from '../useChatPreferencesStore';

describe('useChatPreferencesStore', () => {
  beforeEach(() => {
    useChatPreferencesStore.setState({
      forcedConnectors: [],
      forceWebSearch: false,
    });
  });

  it('starts with no connector forced', () => {
    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([]);
  });

  it('toggles a connector force independently of web search', () => {
    useChatPreferencesStore.getState().toggleForcedConnector('datagouv');

    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([
      'datagouv',
    ]);
    expect(useChatPreferencesStore.getState().forceWebSearch).toBe(false);
  });

  it('toggles each connector on its own', () => {
    const { toggleForcedConnector } = useChatPreferencesStore.getState();
    toggleForcedConnector('datagouv');
    toggleForcedConnector('legi');
    toggleForcedConnector('datagouv');

    expect(useChatPreferencesStore.getState().forcedConnectors).toEqual([
      'legi',
    ]);
  });

  it('carries a stored DataGouv force over to the connector list', async () => {
    localStorage.setItem(
      'chat-preferences',
      JSON.stringify({
        state: { forceDatagouv: true, forceWebSearch: true },
        version: 0,
      }),
    );

    await useChatPreferencesStore.persist.rehydrate();

    const state = useChatPreferencesStore.getState();
    expect(state.forcedConnectors).toEqual(['datagouv']);
    expect(state.forceWebSearch).toBe(true);
    expect(state).not.toHaveProperty('forceDatagouv');
  });
});
