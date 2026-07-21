/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import svgr from 'vite-plugin-svgr';

export default defineConfig({
  plugins: [
    react(),
    // Import `.svg` files as React components, `.svg?url` still resolves to a URL.
    svgr({ include: '**/*.svg' }),
  ],
  resolve: {
    alias: {
      '@': new URL('./src', import.meta.url).pathname,
      // The math extension shipped with remark-math does not support LLM output.
      'micromark-extension-math': 'micromark-extension-llm-math',
    },
    // Prevent a second copy of cunningham-react (pulled by ui-kit) from being bundled.
    dedupe: ['@gouvfr-lasuite/cunningham-react'],
  },
  server: {
    port: 3000,
    host: true,
  },
  preview: {
    port: 3000,
    host: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // fetch-mock's default (server) build requires `node-fetch`; use its browser
    // build, which relies on the global `fetch` provided by jsdom / Node.
    alias: {
      'fetch-mock': 'fetch-mock/esm/client.js',
    },
    coverage: {
      provider: 'v8',
    },
  },
});
