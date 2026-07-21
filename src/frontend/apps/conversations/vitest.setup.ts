import '@testing-library/jest-dom/vitest';

// @testing-library only detects fake timers when a `jest` global exists, and
// falls back to real timers otherwise, which makes `waitFor` hang.
Object.assign(globalThis, {
  jest: { advanceTimersByTime: vi.advanceTimersByTime.bind(vi) },
});
