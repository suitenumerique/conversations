import { Button } from '@openfun/cunningham-react';
import React, { useEffect, useState } from 'react';

import { Box, Icon } from '@/components';

interface ScrollDownProps {
  onClick: () => void;
  containerRef: React.RefObject<HTMLDivElement | null>;
}

export const ScrollDown: React.FC<ScrollDownProps> = ({
  onClick,
  containerRef,
}) => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      if (containerRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
        const isAtBottom = scrollTop + clientHeight >= scrollHeight;
        setIsVisible(!isAtBottom);
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener('scroll', handleScroll, { passive: true });
      setTimeout(handleScroll, 100);

      return () => container.removeEventListener('scroll', handleScroll);
    }
  }, [containerRef]);

  return (
    <Box
      $css={`
        position: absolute;
        bottom: 8px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 1000;
        opacity: ${isVisible ? '1' : '0'};
        transition: opacity 0.3s ease;
        animation: fadeIn 0.3s ease;
        
        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
      `}
    >
      <Button
        className="c__button--bordered"
        aria-label="See more"
        onClick={onClick}
        icon={
          <Icon $variation="800" $theme="primary" iconName="arrow_downward" />
        }
      />
    </Box>
  );
};
