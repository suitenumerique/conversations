import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

const APRIL_FOOLS_MESSAGES = [
  'Destroying all documents in 3...2...1...',
  'Due to budget cuts, I will now only provide 10% of answers',
  "Sorry, I'm a little tired today. Maybe ask another AI?",
];

const REVEAL_MESSAGE = '😄 April Fools! Alright, let me answer for real...';

const CHAR_INTERVAL_MS = 30;
const PAUSE_AFTER_PRANK_MS = 1500;
const PAUSE_AFTER_REVEAL_MS = 1500;
const STORAGE_KEY = 'april-fools-year';
const PENDING_KEY = 'april-fools-pending';

type Phase = 'idle' | 'streaming' | 'pause' | 'reveal' | 'done';

function canRunPrank(): boolean {
  const now = new Date();
  if (now.getMonth() !== 3 || now.getDate() !== 1) return false;

  const year = String(now.getFullYear());
  return localStorage.getItem(STORAGE_KEY) !== year;
}

function markPrankDone(): void {
  localStorage.setItem(STORAGE_KEY, String(new Date().getFullYear()));
}

export function useAprilFools() {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<Phase>('idle');
  const [displayedText, setDisplayedText] = useState('');
  const fullMessageRef = useRef('');
  const charIndexRef = useRef(0);
  const usedRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cleanup = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, []);

  const trigger = useCallback(() => {
    if (usedRef.current || !canRunPrank()) return false;
    usedRef.current = true;
    markPrankDone();

    const translatedMessages = APRIL_FOOLS_MESSAGES.map((msg) => t(msg));
    // not security-sensitive, just picking a random joke
    const msg =
      translatedMessages[Math.floor(Math.random() * translatedMessages.length)]; // NOSONAR
    fullMessageRef.current = msg;
    charIndexRef.current = 0;
    setDisplayedText('');
    setPhase('streaming');

    return true;
  }, [t]);

  // Queue the prank so it survives a navigation remount
  const triggerDeferred = useCallback(() => {
    if (usedRef.current || !canRunPrank()) return;
    sessionStorage.setItem(PENDING_KEY, '1');
  }, []);

  // On mount, check for a deferred trigger
  useEffect(() => {
    if (sessionStorage.getItem(PENDING_KEY)) {
      sessionStorage.removeItem(PENDING_KEY);
      trigger();
    }
  }, [trigger]);

  // Fake-stream the prank message character by character like a legit answer would do
  useEffect(() => {
    if (phase !== 'streaming') return;

    intervalRef.current = setInterval(() => {
      charIndexRef.current += 1;
      const next = fullMessageRef.current.slice(0, charIndexRef.current);
      setDisplayedText(next);

      if (charIndexRef.current >= fullMessageRef.current.length) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        setPhase('pause');
      }
    }, CHAR_INTERVAL_MS);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [phase]);

  // After prank finishes streaming, pause then show reveal
  useEffect(() => {
    if (phase !== 'pause') return;

    timeoutRef.current = setTimeout(() => {
      setDisplayedText((prev) => prev + '\n\n' + t(REVEAL_MESSAGE));
      setPhase('reveal');
    }, PAUSE_AFTER_PRANK_MS);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [phase, t]);

  // After reveal, transition to done
  useEffect(() => {
    if (phase !== 'reveal') return;

    timeoutRef.current = setTimeout(() => {
      setPhase('done');
    }, PAUSE_AFTER_REVEAL_MS);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [phase]);

  // Cleanup on unmount
  useEffect(() => cleanup, [cleanup]);

  const isActive = phase !== 'idle' && phase !== 'done';

  return { phase, displayedText, isActive, trigger, triggerDeferred };
}
