import react from '@vitejs/plugin-react';
import svgr from 'vite-plugin-svgr';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react(), svgr()],
  server: {
    // The dev container publishes 3000 and needs a non-localhost bind.
    port: 3000,
    host: true,
  },
  // Default is node_modules/.vite, which in the dev container is an anonymous
  // volume owned by root while the container runs as the host user: the
  // dependency optimizer cannot write there. This path sits in the bind mount.
  cacheDir: '.vite',
  resolve: {
    alias: {
      '@': new URL('./src', import.meta.url).pathname,
      // Markdown math rendering relies on the LLM-flavoured fork of the
      // micromark math extension; remark-math pulls the upstream one.
      'micromark-extension-math': 'micromark-extension-llm-math',
    },
    // The UI kit ships its own copy of cunningham-react; two copies break the
    // shared React context (theme, modals).
    dedupe: ['@gouvfr-lasuite/cunningham-react'],
  },
  test: {
    alias: {
      // fetch-mock@9's `main` is the node build, which needs node-fetch; the
      // browser build drives jsdom's own fetch. Jest resolved the node one via
      // a node-fetch copy that Next used to hoist.
      'fetch-mock': 'fetch-mock/esm/client.js',
    },
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
