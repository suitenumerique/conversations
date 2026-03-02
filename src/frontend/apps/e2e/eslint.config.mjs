import { playwrightConfig } from 'eslint-config-conversations/playwright.mjs';

export default playwrightConfig({
  tsconfigRootDir: import.meta.dirname,
});
