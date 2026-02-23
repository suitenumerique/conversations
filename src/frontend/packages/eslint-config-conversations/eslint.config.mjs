import prettierRecommended from 'eslint-plugin-prettier/recommended';

import { globalRules, importXConfig } from './common.mjs';

export default [
  { ignores: ['node_modules/**'] },

  // Import-x
  importXConfig,

  // Base rules for JS/MJS config files
  {
    languageOptions: {
      sourceType: 'module',
      ecmaVersion: 'latest',
    },
    rules: globalRules,
  },

  // Prettier (last)
  prettierRecommended,
];
