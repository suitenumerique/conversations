import { useEffect, useState } from 'react';

// Ref globale pour le conteneur de chat
let chatContainerRef: React.RefObject<HTMLDivElement | null> = {
  current: null,
};

export const setChatContainerRef = (
  ref: React.RefObject<HTMLDivElement | null>,
) => {
  chatContainerRef = ref;
  console.log('Chat container ref set:', ref.current);
};

export const useChatScroll = () => {
  const [isAtTop, setIsAtTop] = useState(true);

  useEffect(() => {
    const handleScroll = () => {
      if (chatContainerRef.current) {
        const scrollTop = chatContainerRef.current.scrollTop;
        const newIsAtTop = scrollTop <= 0;
        console.log('Scroll detected:', scrollTop, 'isAtTop:', newIsAtTop);
        setIsAtTop(newIsAtTop);
      }
    };

    // Vérifier si le conteneur existe
    if (chatContainerRef.current) {
      console.log('Setting up scroll listener for container');
      const container = chatContainerRef.current;
      container.addEventListener('scroll', handleScroll, { passive: true });

      // Vérifier la position initiale
      handleScroll();

      return () => {
        console.log('Removing scroll listener');
        container.removeEventListener('scroll', handleScroll);
      };
    } else {
      console.log('No chat container found');
    }
  }, []);

  return { isAtTop };
};
