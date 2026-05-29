import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box } from '@/components';
import { StatusBanner } from '@/core/config/api/useConfig';

const WRAPPER_CSS = `position: absolute;
                  top: 1rem;
                  left: 1.5rem;
                  right: 1.5rem;
                  height: 1.5rem;
                  pointer-events: none;
                  color: var(--c--contextuals--content--semantic--neutral--tertiary);
                  font-size: 1rem;
                  font-family: inherit;
                  line-height: 1.5;
                  overflow: hidden;`;

interface SuggestionCarouselProps {
  messagesLength: number;
  blocked?: boolean;
  banners?: StatusBanner[];
}

export const SuggestionCarousel = ({
  messagesLength,
  blocked = false,
  banners = [],
}: SuggestionCarouselProps) => {
  const { t } = useTranslation();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isResetting, setIsResetting] = useState(false);

  const suggestions = useMemo(
    () => [
      t('Ask a question'),
      t('Turn this list into bullet points'),
      t('Write a short product description'),
      t('Find recent news about...'),
    ],
    [t],
  );

  const bannerItems = useMemo(
    () =>
      banners.flatMap((b) =>
        ([b.title, b.content] as string[]).filter(Boolean),
      ),
    [banners],
  );

  const activeItems = useMemo(
    () => (blocked ? bannerItems : suggestions),
    [blocked, bannerItems, suggestions],
  );

  const carouselItems = useMemo(
    () => (activeItems.length > 0 ? [...activeItems, activeItems[0]] : []),
    [activeItems],
  );

  const carrouselCss = useMemo(
    () => `
    display: flex;
    flex-direction: column;
    height: ${(activeItems.length + 1) * 100}%;
    transform: translateY(-${currentIndex * (100 / (activeItems.length + 1))}%);
    transition: ${isResetting ? 'none' : 'transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)'};
  `,
    [currentIndex, isResetting, activeItems.length],
  );

  const itemCss = useMemo(
    () => `
    height: calc(100% / ${activeItems.length + 1});
    flex-shrink: 0;
    white-space: nowrap;
    color: var(--c--contextuals--content--semantic--neutral--tertiary) !important;
    display: flex;
    justify-content: flex-start;
  `,
    [activeItems.length],
  );

  // Reset position when switching between blocked/unblocked
  useEffect(() => {
    setCurrentIndex(0);
    setIsResetting(false);
  }, [blocked]);

  useEffect(() => {
    if (!blocked && messagesLength !== 0) return;
    if (activeItems.length <= 1) return;
    const interval = setInterval(() => {
      setCurrentIndex((prev) =>
        prev === activeItems.length - 1 ? activeItems.length : prev + 1,
      );
    }, 3000);
    return () => clearInterval(interval);
  }, [blocked, messagesLength, activeItems.length]);

  useEffect(() => {
    if (currentIndex === activeItems.length) {
      const timeout = setTimeout(() => {
        setIsResetting(true);
        setCurrentIndex(0);
        setTimeout(() => setIsResetting(false), 50);
      }, 500);
      return () => clearTimeout(timeout);
    }
  }, [currentIndex, activeItems.length]);

  if (activeItems.length === 0) return null;

  return (
    <Box $css={WRAPPER_CSS}>
      <Box $css={carrouselCss}>
        {carouselItems.map((item, index) => (
          <Box key={index} $css={itemCss}>
            {item}
          </Box>
        ))}
      </Box>
    </Box>
  );
};
SuggestionCarousel.displayName = 'SuggestionCarousel';
