import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Text } from '@/components';
import { ArenaAcknowledgement } from '@/features/chat/api/useArena';

/** How long the card stays fully visible before it collapses. */
export const ARENA_THANKS_VISIBLE_MS = 5000;
/** Duration of the slide-in / slide-out transition. */
const TRANSITION_MS = 300;
const REDUCED_MOTION_MS = 150;

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export interface ArenaThanksProps {
  acknowledgement: ArenaAcknowledgement;
  /** The card has collapsed: the parent can unmount it. */
  onDone?: () => void;
  visibleMs?: number;
}

type Phase = 'enter' | 'shown' | 'leave';

/**
 * A one-off check mark drawn with CSS: the only Lottie shipped with the app
 * is the "searching" loader, which is not a check mark, so this stays in
 * plain SVG (no extra asset, no lazy chunk).
 */
const CheckMark = ({ animate }: { animate: boolean }) => (
  <Box
    aria-hidden="true"
    data-testid="arena-thanks-check"
    $css={`
      flex: 0 0 auto;
      width: 22px;
      height: 22px;
      color: var(--c--contextuals--content--semantic--brand--primary, #5e5cd0);

      & circle {
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        ${animate ? 'stroke-dasharray: 76; stroke-dashoffset: 76; animation: arena-check-draw 0.4s ease-out forwards;' : ''}
      }
      & path {
        fill: none;
        stroke: currentColor;
        stroke-width: 2.5;
        stroke-linecap: round;
        stroke-linejoin: round;
        ${animate ? 'stroke-dasharray: 20; stroke-dashoffset: 20; animation: arena-check-draw 0.3s ease-out 0.3s forwards;' : ''}
      }
      @keyframes arena-check-draw {
        to {
          stroke-dashoffset: 0;
        }
      }
    `}
  >
    <svg viewBox="0 0 28 28" width="28" height="28" focusable="false">
      <circle cx="14" cy="14" r="12" />
      <path d="M8 14.5l4 4 8-8" />
    </svg>
  </Box>
);

/** One clear, scannable number: the value people actually look for. */
const Stat = ({ value, label }: { value: string; label: string }) => (
  <Box $gap="2px" $css="min-width: 0;">
    <Text
      $css={`
        color: var(--c--contextuals--content--semantic--brand--primary, #5e5cd0);
        font-weight: 600;
        line-height: 1.1;
      `}
      $size="md"
    >
      {value}
    </Text>
    <Text
      $css="color: var(--c--contextuals--content--surface--secondary, #666); line-height: 1.1;"
      $size="xs"
    >
      {label}
    </Text>
  </Box>
);

/**
 * Vote-confirmation toast shown after an arena vote, pinned to the top-right
 * of the viewport. Leads with a short thank-you and two scannable numbers —
 * the votes this user has cast, and the votes everyone has cast on this
 * experiment — rather than a sentence to read every time. Slides in, stays
 * for about five seconds, then slides back out. Honours
 * `prefers-reduced-motion`: no sliding, just a fade.
 */
export const ArenaThanks = ({
  acknowledgement,
  onDone,
  visibleMs = ARENA_THANKS_VISIBLE_MS,
}: ArenaThanksProps) => {
  const { t, i18n } = useTranslation();
  const [phase, setPhase] = useState<Phase>('enter');
  const reduced = useRef(prefersReducedMotion()).current;
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    // Let the collapsed state paint once so the opening transitions.
    const enter = setTimeout(() => setPhase('shown'), 20);
    const leave = setTimeout(() => setPhase('leave'), visibleMs);
    const done = setTimeout(
      () => onDoneRef.current?.(),
      visibleMs + (reduced ? REDUCED_MOTION_MS : TRANSITION_MS),
    );
    return () => {
      clearTimeout(enter);
      clearTimeout(leave);
      clearTimeout(done);
    };
  }, [visibleMs, reduced]);

  const { user_votes, experiment_votes, milestone } = acknowledgement;

  const locale = i18n?.language;
  const format = (value: number) => value.toLocaleString(locale);

  let title: string;
  switch (milestone) {
    case 'first_vote':
      title = t('First vote, thank you!');
      break;
    case 'tenth_vote':
      title = t('Ten votes already, thank you!');
      break;
    case 'hundredth_vote':
      title = t('A hundred votes, thank you!');
      break;
    default:
      title = t('Thanks, your vote is recorded');
  }

  const visible = phase === 'shown';
  const duration = reduced ? REDUCED_MOTION_MS : TRANSITION_MS;

  return (
    <Box
      role="status"
      data-testid="arena-thanks"
      data-phase={phase}
      $css={`
        box-sizing: border-box;
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 1000;
        max-width: 360px;
        pointer-events: none;
        opacity: ${visible ? 1 : 0};
        transform: ${visible || reduced ? 'none' : 'translateX(24px)'};
        transition:
          opacity ${duration}ms ease,
          transform ${duration}ms ease;
      `}
    >
      <Box
        $gap="10px"
        $padding={{ vertical: '12px', horizontal: '16px' }}
        $radius="12px"
        $css={`
          background: var(--c--contextuals--background--semantic--brand--tertiary, #eef1fa);
          border: 1px solid var(--c--contextuals--background--semantic--brand--secondary, #dde2f5);
          box-shadow: 0 4px 16px rgba(94, 92, 208, 0.12);
        `}
      >
        <Box $direction="row" $align="center" $gap="8px">
          <CheckMark animate={!reduced} />
          <Text
            $css="color: var(--c--contextuals--content--surface--primary, #1a1a1a); font-weight: 600;"
            $size="sm"
          >
            {title}
          </Text>
        </Box>

        <Box $direction="row" $align="center" $gap="20px">
          <Stat value={format(user_votes)} label={t('Your votes in total')} />
          <Stat
            value={format(experiment_votes)}
            label={t('Votes on this test')}
          />
        </Box>
      </Box>
    </Box>
  );
};
