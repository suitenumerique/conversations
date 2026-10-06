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

  it('starts on Auto, with no conversation owning the tier', () => {
    const state = useChatPreferencesStore.getState();
    expect(state.selectedTier).toBe('auto');
    expect(state.tierConversationId).toBeNull();
  });

  it('pins a tier to a conversation and keeps the owner when omitted', () => {
    useChatPreferencesStore.getState().setSelectedTier('complex', 'conv-1');
    expect(useChatPreferencesStore.getState()).toMatchObject({
      selectedTier: 'complex',
      tierConversationId: 'conv-1',
    });

    useChatPreferencesStore.getState().setSelectedTier('auto');
    expect(useChatPreferencesStore.getState()).toMatchObject({
      selectedTier: 'auto',
      tierConversationId: 'conv-1',
    });
  });

  it('hands a pin made on the new-chat screen to the created conversation', () => {
    useChatPreferencesStore.getState().setSelectedTier('simple', null);
    useChatPreferencesStore.getState().adoptTierConversation('conv-2');

    expect(useChatPreferencesStore.getState()).toMatchObject({
      selectedTier: 'simple',
      tierConversationId: 'conv-2',
    });
  });

  it('remembers that the router intro was seen', () => {
    useChatPreferencesStore.getState().markRouterIntroSeen();
    expect(useChatPreferencesStore.getState().hasSeenRouterIntro).toBe(true);
  });
});
