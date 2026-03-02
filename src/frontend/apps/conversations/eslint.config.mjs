import { nextConfig } from 'eslint-config-conversations/next.mjs';

export default nextConfig({
  tsconfigRootDir: import.meta.dirname,
  nextRootDir: import.meta.dirname,
});
