// The `@testing-library/jest-dom/vitest` entry point is hoisted to the
// workspace root, where it cannot resolve `vitest` (kept in this app's own
// node_modules), so register the matchers explicitly from here instead.
import * as matchers from '@testing-library/jest-dom/matchers';
import { expect } from 'vitest';

expect.extend(matchers);

// lottie-web (pulled in by the Loader) draws on a probe canvas as soon as it is
// imported, and jsdom returns no 2D context. Hand it a no-op one.
HTMLCanvasElement.prototype.getContext = (() =>
  new Proxy(
    {},
    {
      get: () => () => undefined,
      set: () => true,
    },
  )) as unknown as HTMLCanvasElement['getContext'];
