import { Tooltip } from '@gouvfr-lasuite/cunningham-react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';
import { RoutingEvent } from '@/features/chat/api/useChat';
import { TierSlug } from '@/features/chat/types';

/** Model wording of each tier in the caption ("Auto · Reasoning model"). */
const TIER_MODEL_LABELS: Record<TierSlug, string> = {
  auto: 'Auto',
  simple: 'Fast model',
  standard: 'Balanced model',
  complex: 'Reasoning model',
};

/** Bars lit in the pictogram: ordinal, matching the selector's leaves. */
const TIER_LEVEL: Record<TierSlug, number> = {
  auto: 0,
  simple: 1,
  standard: 2,
  complex: 3,
};

const CAPTION_CSS = `
  font-size: 12px;
  line-height: 16px;
  color: var(--c--contextuals--content--semantic--neutral--tertiary);
  cursor: default;
`;

// A focusable trigger so the tooltip also opens on keyboard focus.
const CAPTION_BUTTON_CSS = `
  all: unset;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 4px;
  ${CAPTION_CSS}
  &:focus-visible {
    outline: 2px solid var(--c--contextuals--border--semantic--brand--primary);
    outline-offset: 2px;
  }
`;

const SHIMMER_CSS = `
  ${CAPTION_CSS}
  background: linear-gradient(
    90deg,
    var(--c--contextuals--content--semantic--neutral--tertiary) 0%,
    var(--c--contextuals--content--semantic--neutral--tertiary) 35%,
    var(--c--contextuals--content--semantic--neutral--primary) 50%,
    var(--c--contextuals--content--semantic--neutral--tertiary) 65%,
    var(--c--contextuals--content--semantic--neutral--tertiary) 100%
  );
  background-size: 200% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: routing-caption-shimmer 1.4s linear infinite;

  @keyframes routing-caption-shimmer {
    from {
      background-position: 200% 0;
    }
    to {
      background-position: -200% 0;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    animation: none;
    -webkit-text-fill-color: initial;
    background: none;
  }
`;

const pictogramCss = (animate: boolean) => `
  flex: 0 0 auto;
  width: 12px;
  height: 12px;
  color: var(--c--contextuals--content--semantic--neutral--secondary);

  & rect {
    fill: currentColor;
    transform-origin: bottom;
    transform-box: fill-box;
  }
  & rect.tier-pictogram-off {
    opacity: 0.3;
  }
  ${
    animate
      ? `
  & rect.tier-pictogram-on {
    animation: tier-pictogram-grow 150ms ease-out;
  }
  @keyframes tier-pictogram-grow {
    from {
      transform: scaleY(0.3);
    }
    to {
      transform: scaleY(1);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    & rect.tier-pictogram-on {
      animation: none;
    }
  }
  `
      : ''
  }
`;

/** One to three bars, lit up to the tier's level. */
export const TierPictogram = ({
  tier,
  animate = false,
}: {
  tier: TierSlug;
  animate?: boolean;
}) => {
  const level = TIER_LEVEL[tier];
  const bars = [
    { x: 0, height: 5 },
    { x: 4.5, height: 8 },
    { x: 9, height: 12 },
  ];
  return (
    <Box
      as="span"
      $css={pictogramCss(animate)}
      data-testid="tier-pictogram"
      data-tier={tier}
      aria-hidden
    >
      <svg viewBox="0 0 12 12" width="12" height="12" focusable="false">
        {bars.map((bar, index) => (
          <rect
            key={bar.x}
            className={
              index < level ? 'tier-pictogram-on' : 'tier-pictogram-off'
            }
            data-testid={index < level ? 'tier-bar-on' : 'tier-bar-off'}
            x={bar.x}
            y={12 - bar.height}
            width="3"
            height={bar.height}
            rx="0.75"
          />
        ))}
      </svg>
    </Box>
  );
};

interface RoutingCaptionProps {
  /** The decision; when absent and `pending`, the shimmer line is shown. */
  routing?: RoutingEvent;
  /** The router is still choosing (no decision yet). */
  pending?: boolean;
}

/**
 * The router decision of an assistant answer: a shimmer while the router runs,
 * then the tier pictogram and "Auto · <model>" (or "<model> · your choice" when
 * the user pinned the tier, "<model> · needed for this request" when a
 * constraint raised the tier), with a tooltip that explains the choice. Same
 * 12px style as the leaf row.
 */
export const RoutingCaption = ({ routing, pending }: RoutingCaptionProps) => {
  const { t } = useTranslation();

  if (!routing) {
    if (!pending) {
      return null;
    }
    return (
      <Text
        as="span"
        $css={SHIMMER_CSS}
        data-testid="routing-caption-pending"
        role="status"
      >
        {t('Choosing the model…')}
      </Text>
    );
  }

  const model = t(TIER_MODEL_LABELS[routing.tier]);
  let text: string;
  if (routing.tier_source === 'user') {
    text = t('{{model}} · your choice', { model });
  } else if (routing.tier_source === 'constraint') {
    // Raised above the pinned or Auto tier by a capability the turn needs.
    text = t('{{model}} · needed for this request', { model });
  } else {
    text = t('Auto · {{model}}', { model });
  }

  return (
    <Tooltip
      placement="top"
      content={t(
        'The assistant chose this model for this question so as to use just what is needed.',
      )}
    >
      <Box
        as="button"
        type="button"
        $css={CAPTION_BUTTON_CSS}
        data-testid="routing-caption"
        data-tier-source={routing.tier_source}
      >
        <TierPictogram tier={routing.tier} animate={!!routing.changed} />
        <Text as="span" $css="font-size: inherit; color: inherit;">
          {text}
        </Text>
      </Box>
    </Tooltip>
  );
};
