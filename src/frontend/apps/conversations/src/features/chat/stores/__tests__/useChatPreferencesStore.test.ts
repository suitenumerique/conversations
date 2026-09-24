import { useChatPreferencesStore } from '../useChatPreferencesStore';

describe('useChatPreferencesStore', () => {
  it('starts with the DataGouv connector unforced', () => {
    expect(useChatPreferencesStore.getState().forceDatagouv).toBe(false);
  });

  it('toggles the DataGouv force independently of web search', () => {
    useChatPreferencesStore.getState().toggleForceDatagouv();

    expect(useChatPreferencesStore.getState().forceDatagouv).toBe(true);
    expect(useChatPreferencesStore.getState().forceWebSearch).toBe(false);
  });
});
