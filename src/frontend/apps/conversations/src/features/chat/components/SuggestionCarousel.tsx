import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box } from '@/components';

const SUGGESTIONS_COUNT = 4;

const WRAPPER_CSS = `position: absolute;
                  top: 1rem;
                  left: 1.5rem;
                  right: 1.5rem;
                  height: 1.5rem;
                  pointer-events: none;
                  color: var(--c--theme--colors--greyscale-500);
                  font-size: 1rem;
                  font-family: inherit;
                  line-height: 1.5;
                  overflow: hidden;`;

const ITEM_CSS = `
  height: calc(100% / ${SUGGESTIONS_COUNT + 1});
  flex-shrink: 0;
  white-space: nowrap;
  display: flex;
  justify-content: flex-start;
`;

interface SuggestionCarouselProps {
  messagesLength: number;
}

export const SuggestionCarousel = ({
  messagesLength,
}: SuggestionCarouselProps) => {
  const { t } = useTranslation();
  const [currentSuggestionIndex, setCurrentSuggestionIndex] = useState(0);
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
  const carouselSuggestions = useMemo(
    () => [...suggestions, suggestions[0]],
    [suggestions],
  );

  const carrouselCss = useMemo(
    () => `
    display: flex;
    flex-direction: column;
    height: ${(SUGGESTIONS_COUNT + 1) * 100}%;
    transform: translateY(-${currentSuggestionIndex * (100 / (SUGGESTIONS_COUNT + 1))}%);
    transition: ${isResetting ? 'none' : 'transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)'};
  `,
    [currentSuggestionIndex, isResetting],
  );

  useEffect(() => {
    if (messagesLength === 0) {
      const interval = setInterval(() => {
        setCurrentSuggestionIndex((prev) => {
          if (prev === SUGGESTIONS_COUNT - 1) {
            return SUGGESTIONS_COUNT;
          }
          return prev + 1;
        });
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [messagesLength]);

  useEffect(() => {
    if (currentSuggestionIndex === suggestions.length) {
      const timeout = setTimeout(() => {
        setIsResetting(true);
        setCurrentSuggestionIndex(0);
        setTimeout(() => setIsResetting(false), 50);
      }, 500);
      return () => clearTimeout(timeout);
    }
  }, [currentSuggestionIndex, suggestions.length]);

  return (
    <Box $css={WRAPPER_CSS}>
      <Box $css={carrouselCss}>
        {carouselSuggestions.map((suggestion, index) => (
          <Box key={index} $css={ITEM_CSS}>
            {suggestion}
          </Box>
        ))}
      </Box>
    </Box>
  );
};
SuggestionCarousel.displayName = 'SuggestionCarousel';
