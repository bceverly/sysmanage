// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import js from '@eslint/js';
import typescript from '@typescript-eslint/eslint-plugin';
import typescriptParser from '@typescript-eslint/parser';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import security from 'eslint-plugin-security';
import i18next from 'eslint-plugin-i18next';

export default [
  {
    // Top-level ignores — applies to every block below.  Without this,
    // ``js.configs.recommended`` falls back to scanning vendored
    // ``dist/`` bundles where browser globals aren't declared, flooding
    // the report with thousands of false-positive ``no-undef``s.
    ignores: [
      'dist/**',
      'node_modules/**',
      'coverage/**',
      'plugin-dist/**',
      'public/locales/**',
      '*.config.js',
      'vite.config.ts',
      'vitest.config.ts',
      'playwright.config.ts',
    ],
  },
  js.configs.recommended,
  {
    files: ['src/**/*.{js,jsx,ts,tsx}'],
    ignores: ['src/**/*.test.{js,jsx,ts,tsx}', 'src/__tests__/**/*'],
    linterOptions: {
      // Disable reporting of unused disable directives - some are for security lint config
      reportUnusedDisableDirectives: 'off'
    },
    languageOptions: {
      parser: typescriptParser,
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: {
          jsx: true
        }
      },
      globals: {
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        process: 'readonly',
        localStorage: 'readonly',
        // Storage: the interface type of localStorage/sessionStorage, referenced
        // as a type annotation by the in-memory polyfill in setupTests.ts.
        Storage: 'readonly',
        alert: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        // DOM element types — needed by useRef<HTML*Element> generics
        HTMLElement: 'readonly',
        HTMLInputElement: 'readonly',
        HTMLFormElement: 'readonly',
        HTMLImageElement: 'readonly',
        HTMLDivElement: 'readonly',
        HTMLButtonElement: 'readonly',
        HTMLAnchorElement: 'readonly',
        HTMLSpanElement: 'readonly',
        HTMLLabelElement: 'readonly',
        // DOM event types — ``Event`` deliberately omitted; HostDetail.tsx
        // and a few other files declare their own ``Event`` interface for
        // domain-specific payloads, and adding it here would cause
        // ``no-redeclare`` errors.
        MouseEvent: 'readonly',
        KeyboardEvent: 'readonly',
        FocusEvent: 'readonly',
        Node: 'readonly',
        EventTarget: 'readonly',
        // Browser APIs used directly without import
        FormData: 'readonly',
        AbortController: 'readonly',
        Blob: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        ResizeObserver: 'readonly',
        MutationObserver: 'readonly',
        IntersectionObserver: 'readonly',
        fetch: 'readonly'
      }
    },
    plugins: {
      '@typescript-eslint': typescript,
      'react': react,
      'react-hooks': reactHooks,
      'security': security,
      'i18next': i18next
    },
    rules: {
      ...typescript.configs.recommended.rules,
      ...react.configs.recommended.rules,
      // React Hooks rules - explicitly defined since spreading config doesn't work in flat config
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
      'react/no-unescaped-entities': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { 'argsIgnorePattern': '^_' }],
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/ban-ts-comment': 'warn',
      '@typescript-eslint/no-wrapper-object-types': 'off',
      // Security plugin rule - disabled by default, but plugin needed for eslint-disable comments
      'security/detect-possible-timing-attacks': 'off',
      // i18n guard: flag hardcoded user-facing text in JSX so it can't ship
      // un-externalized.  jsx-text-only = literal text directly inside JSX
      // elements (the common case), without the false positives of logic/value
      // string literals.  Intentional non-translatable text (brand names, etc.)
      // gets a `// eslint-disable-next-line i18next/no-literal-string`.
      'i18next/no-literal-string': ['error', { mode: 'jsx-text-only' }]
    },
    settings: {
      react: {
        version: 'detect'
      }
    }
  },
  {
    files: ['src/**/*.test.{js,jsx,ts,tsx}', 'src/__tests__/**/*'],
    languageOptions: {
      parser: typescriptParser,
      globals: {
        vi: 'readonly',
        describe: 'readonly',
        test: 'readonly',
        it: 'readonly',
        expect: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
        jest: 'readonly',
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        HTMLInputElement: 'readonly',
        setTimeout: 'readonly',
        URL: 'readonly'
      }
    },
    plugins: {
      '@typescript-eslint': typescript,
      'react': react
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      'react/prop-types': 'off'
    }
  }
];