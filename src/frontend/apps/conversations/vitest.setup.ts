// The `@testing-library/jest-dom/vitest` entry point is hoisted to the
// workspace root, where it cannot resolve `vitest` (kept in this app's own
// node_modules), so register the matchers explicitly from here instead.
import * as matchers from '@testing-library/jest-dom/matchers';
import { expect } from 'vitest';

expect.extend(matchers);
