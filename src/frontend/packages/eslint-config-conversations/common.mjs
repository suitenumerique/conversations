import tsPlugin from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import importXPlugin from 'eslint-plugin-import-x';

// Base import-x plugin config (included in all profiles)
export const importXConfig = {
  plugins: {
    'import-x': importXPlugin,
  },
};

// Rules shared across all profiles
export const globalRules = {
  'block-scoped-var': 'error',
  curly: ['error', 'all'],
  'import-x/no-duplicates': ['error', { considerQueryString: false }],
  'import-x/order': [
    'error',
    {
      alphabetize: { order: 'asc' },
      groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
      pathGroups: [{ pattern: '@/**', group: 'internal' }],
      pathGroupsExcludedImportTypes: ['builtin'],
      'newlines-between': 'always',
      warnOnUnassignedImports: true,
    },
  ],
  'no-alert': 'error',
  'no-unused-vars': [
    'error',
    { varsIgnorePattern: '^_', argsIgnorePattern: '^_' },
  ],
  'no-var': 'error',
  'sort-imports': ['error', { ignoreDeclarationSort: true }],
};

// React-specific global rules (for profiles using React)
export const reactGlobalRules = {
  'react/jsx-curly-brace-presence': [
    'error',
    { props: 'never', children: 'never', propElementValues: 'always' },
  ],
};

// TypeScript configs factory - returns flat config array
export function typescriptConfigs(tsconfigRootDir) {
  return [
    ...tsPlugin.configs['flat/recommended-type-checked'],
    {
      files: ['**/*.{ts,tsx,mts,cts}'],
      languageOptions: {
        parser: tsParser,
        parserOptions: {
          projectService: true,
          tsconfigRootDir,
        },
      },
      rules: {
        '@typescript-eslint/no-explicit-any': 'error',
        '@typescript-eslint/no-non-null-assertion': 'error',
        '@typescript-eslint/no-unused-vars': [
          'error',
          { varsIgnorePattern: '^_', argsIgnorePattern: '^_' },
        ],
        'sort-imports': ['error', { ignoreDeclarationSort: true }],
      },
    },
    {
      files: ['**/*.d.ts'],
      rules: { 'no-unused-vars': 'off' },
    },
    // Disable type-checked rules for JS/MJS/CJS files (e.g. eslint.config.mjs)
    {
      files: ['**/*.{js,mjs,cjs}'],
      ...tsPlugin.configs['flat/disable-type-checked'],
    },
  ];
}
