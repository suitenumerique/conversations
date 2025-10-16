import { useScrollStore } from '../stores/useScrollStore';

export const useChatScroll = () => {
  const { isAtTop } = useScrollStore();
  return { isAtTop };
};
