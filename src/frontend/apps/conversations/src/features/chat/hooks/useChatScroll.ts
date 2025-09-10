import { useEffect, useState } from 'react';

// Ref globale pour le conteneur de chat
let chatContainerRef: React.RefObject<HTMLDivElement | null> = {
  current: null,
};

export const setChatContainerRef = (
  ref: React.RefObject<HTMLDivElement | null>,
) => {
  chatContainerRef = ref;
};

export const useChatScroll = () => {
  const [isAtTop, setIsAtTop] = useState(true);

  useEffect(() => {
    const handleScroll = () => {
      if (chatContainerRef.current) {
        const scrollTop = chatContainerRef.current.scrollTop;
        const newIsAtTop = scrollTop <= 5;
        setIsAtTop(newIsAtTop);
      }
    };

    // Attendre que le conteneur soit disponible
    const checkContainer = () => {
      if (chatContainerRef.current) {
        const container = chatContainerRef.current;
        container.addEventListener('scroll', handleScroll, { passive: true });

        // Vérifier la position initiale
        handleScroll();

        return () => {
          container.removeEventListener('scroll', handleScroll);
        };
      } else {
        // Réessayer après un court délai si le conteneur n'est pas encore disponible
        const timeoutId = setTimeout(checkContainer, 100);
        return () => clearTimeout(timeoutId);
      }
    };

    return checkContainer();
  }, []);

  return { isAtTop };
};
