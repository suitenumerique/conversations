// hooks/useElementHeight.ts
import { useState, useEffect, useRef, RefObject } from 'react';

export function useElementHeight<T extends HTMLElement>(): [
  RefObject<T>,
  number,
] {
  const ref = useRef<T>(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setHeight(entry.contentRect.height);
      }
    });

    observer.observe(element);
    setHeight(element.offsetHeight); // initial measurement

    return () => observer.disconnect();
  }, []);

  return [ref, height];
}
