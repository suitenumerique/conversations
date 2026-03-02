import playwrightPlugin from 'eslint-plugin-playwright';
import prettierRecommended from 'eslint-plugin-prettier/recommended';
import reactPlugin from 'eslint-plugin-react';
import globals from 'globals';

import { globalRules, importXConfig, typescriptConfigs } from './common.mjs';

export function playwrightConfig({ tsconfigRootDir }) {
  return [
    // Ignores
    { ignores: ['coverage/', 'report/', 'screenshots/', 'test-results/'] },

    // React (for JSX parsing support)
    reactPlugin.configs.flat.recommended,
    { settings: { react: { version: 'detect' } } },

    // Import-x
    importXConfig,

    // Browser + Node globals + base rules
    {
      languageOptions: {
        globals: {
          ...globals.browser,
          ...globals.node,
        },
      },
      rules: globalRules,
    },

    // TypeScript
    ...typescriptConfigs(tsconfigRootDir),

    // Relax TS rules for all TS files in e2e
    {
      files: ['**/*.ts'],
      rules: {
        '@typescript-eslint/no-unsafe-member-access': 'off',
      },
    },

    // Playwright test files
    {
      files: ['**/*.spec.*', '**/*.test.*', '**/__mock__/**/*'],
      ...playwrightPlugin.configs['flat/recommended'],
      rules: {
        ...playwrightPlugin.configs['flat/recommended'].rules,
        '@typescript-eslint/no-unsafe-member-access': 'off',
        '@typescript-eslint/no-unsafe-assignment': 'off',
        '@typescript-eslint/no-non-null-assertion': 'off',
      },
    },

    // Prettier (last)
    prettierRecommended,
  ];
}
