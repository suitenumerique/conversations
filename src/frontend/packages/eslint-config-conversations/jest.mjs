import jestPlugin from 'eslint-plugin-jest';
import prettierRecommended from 'eslint-plugin-prettier/recommended';
import reactPlugin from 'eslint-plugin-react';
import testingLibraryPlugin from 'eslint-plugin-testing-library';

import {
  globalRules,
  importXConfig,
  reactGlobalRules,
  typescriptConfigs,
} from './common.mjs';

const testFilePatterns = ['**/*.spec.*', '**/*.test.*', '**/__mocks__/**/*'];

// Test-specific configs (reused by next.mjs for test file overrides)
export function jestTestConfigs() {
  return [
    {
      files: testFilePatterns,
      ...jestPlugin.configs['flat/recommended'],
      rules: {
        ...jestPlugin.configs['flat/recommended'].rules,
        '@typescript-eslint/no-empty-function': 'off',
        '@typescript-eslint/no-explicit-any': 'off',
        '@typescript-eslint/no-non-null-assertion': 'off',
        '@typescript-eslint/no-unsafe-argument': 'off',
        '@typescript-eslint/no-unsafe-assignment': 'off',
        '@typescript-eslint/no-unsafe-call': 'off',
        '@typescript-eslint/no-unsafe-member-access': 'off',
        '@typescript-eslint/no-unsafe-return': 'off',
        '@typescript-eslint/no-unused-vars': [
          'error',
          { varsIgnorePattern: '^_', argsIgnorePattern: '^_' },
        ],
        '@typescript-eslint/unbound-method': 'off',
        'jest/expect-expect': 'error',
        'jest/unbound-method': 'error',
        'react/display-name': 0,
        'react/react-in-jsx-scope': 'off',
      },
    },
    {
      files: testFilePatterns,
      ...testingLibraryPlugin.configs['flat/react'],
      rules: {
        ...testingLibraryPlugin.configs['flat/react'].rules,
        'testing-library/no-await-sync-events': [
          'error',
          { eventModules: ['fire-event'] },
        ],
        'testing-library/await-async-events': [
          'error',
          { eventModule: 'userEvent' },
        ],
        'testing-library/no-manual-cleanup': 'off',
      },
    },
  ];
}

// Full jest profile (standalone use for packages like i18n)
export function jestConfig(tsconfigRootDir) {
  return [
    { ignores: ['node_modules/**'] },

    // React
    reactPlugin.configs.flat.recommended,
    { settings: { react: { version: 'detect' } } },

    // Import-x
    importXConfig,

    // Base rules
    {
      rules: {
        ...globalRules,
        ...reactGlobalRules,
      },
    },

    // TypeScript
    ...typescriptConfigs(tsconfigRootDir),

    // Test overrides
    ...jestTestConfigs(),

    // Prettier (last)
    prettierRecommended,
  ];
}
