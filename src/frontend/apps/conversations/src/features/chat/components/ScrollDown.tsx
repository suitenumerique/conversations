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
        const isAtBottom = scrollTop + clientHeight >= scrollHeight - 25;
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
        pointer-events: ${isVisible ? 'auto' : 'none'};
      `}
    >
      <Button
        className="c__button--bordered"
        aria-label="See more"
        onClick={onClick}
        icon={
          <Icon $variation="text" $theme="primary" iconName="arrow_downward" />
        }
      />
    </Box>
  );
};
