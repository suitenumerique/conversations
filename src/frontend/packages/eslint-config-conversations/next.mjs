import nextPlugin from '@next/eslint-plugin-next';
import queryPlugin from '@tanstack/eslint-plugin-query';
import jsxA11yPlugin from 'eslint-plugin-jsx-a11y';
import prettierRecommended from 'eslint-plugin-prettier/recommended';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import globals from 'globals';

import {
  globalRules,
  importXConfig,
  reactGlobalRules,
  typescriptConfigs,
} from './common.mjs';
import { jestTestConfigs } from './jest.mjs';

export function nextConfig({ tsconfigRootDir, nextRootDir }) {
  return [
    // Ignores
    {
      ignores: ['.next/', '.swc/', 'out/', 'coverage/', 'service-worker.js'],
    },

    // Next.js plugin
    nextPlugin.flatConfig.recommended,

    // React
    reactPlugin.configs.flat.recommended,
    reactPlugin.configs.flat['jsx-runtime'],

    // React hooks (only classic rules; v7 Compiler rules can be opted-in later)
    {
      plugins: { 'react-hooks': reactHooksPlugin },
      rules: {
        'react-hooks/rules-of-hooks': 'error',
        'react-hooks/exhaustive-deps': 'error',
      },
    },

    // JSX A11y
    {
      ...jsxA11yPlugin.flatConfigs.recommended,
      settings: {
        ...jsxA11yPlugin.flatConfigs.recommended.settings,
        'jsx-a11y': {
          polymorphicPropName: 'as',
          components: {
            Input: 'input',
            Button: 'button',
            Box: 'div',
            Text: 'span',
            Select: 'select',
          },
        },
      },
    },

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
      settings: {
        react: { version: 'detect' },
        next: { rootDir: nextRootDir },
      },
      rules: {
        ...globalRules,
        ...reactGlobalRules,
      },
    },

    // TypeScript
    ...typescriptConfigs(tsconfigRootDir),

    // Test files (Jest)
    ...jestTestConfigs(),

    // TanStack Query
    ...queryPlugin.configs['flat/recommended'],

    // Prettier (must be last)
    prettierRecommended,
  ];
}
