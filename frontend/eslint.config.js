import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import security from 'eslint-plugin-security';
import globals from 'globals';
import tseslint from 'typescript-eslint';

const fetchMessage = 'Use shared/api-client instead of raw fetch.';
const storageMessage = 'Tokens/state must not be stored in web storage (use HttpOnly cookies).';
const globalObjects = ['window', 'globalThis', 'self'];

// LIMITATION: only direct accesses are detected (fetch, window.fetch, globalThis["fetch"]...).
// Indirect access (const w = window; w.fetch(...), destructuring such as
// const { fetch: f } = window, aliasing via function arguments) is NOT detected by these rules
// and depends on code review.
const networkMessage = 'Network access must go through shared/api-client.';
const networkGlobalNames = ['XMLHttpRequest', 'WebSocket'];
// indexedDB is only allowed in shared/offline (the single place for offline storage).
const indexedDbMessage = 'indexedDB is only allowed inside shared/offline.';

const fetchGlobal = { name: 'fetch', message: fetchMessage };
const networkGlobals = networkGlobalNames.map((name) => ({ name, message: networkMessage }));
const indexedDbGlobal = { name: 'indexedDB', message: indexedDbMessage };
const storageGlobals = ['localStorage', 'sessionStorage'].map((name) => ({
  name,
  message: storageMessage,
}));
const fetchProperties = globalObjects.map((object) => ({
  object,
  property: 'fetch',
  message: fetchMessage,
}));
const networkProperties = [
  ...globalObjects.flatMap((object) =>
    networkGlobalNames.map((property) => ({ object, property, message: networkMessage })),
  ),
  { object: 'navigator', property: 'sendBeacon', message: networkMessage },
];
const indexedDbProperties = globalObjects.map((object) => ({
  object,
  property: 'indexedDB',
  message: indexedDbMessage,
}));
const storageProperties = globalObjects.flatMap((object) =>
  ['localStorage', 'sessionStorage'].map((property) => ({
    object,
    property,
    message: storageMessage,
  })),
);

export default tseslint.config(
  {
    ignores: [
      'dist',
      'coverage',
      'node_modules',
      'playwright-report',
      'test-results',
      'tests/fixtures',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  react.configs.flat.recommended,
  react.configs.flat['jsx-runtime'],
  reactHooks.configs.flat.recommended,
  security.configs.recommended,
  {
    languageOptions: { globals: { ...globals.browser } },
    settings: { react: { version: 'detect' } },
    rules: {
      'react/no-danger': 'error',
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-restricted-globals': ['error', ...storageGlobals],
      'no-restricted-properties': ['error', ...storageProperties],
    },
  },
  {
    // Raw network access is only allowed inside the central api-client; indexedDB only in
    // shared/offline. (Flat config replaces rule options, so every ban is repeated per block.)
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/shared/api-client/**', 'src/shared/offline/**'],
    rules: {
      'no-restricted-globals': [
        'error',
        fetchGlobal,
        ...networkGlobals,
        indexedDbGlobal,
        ...storageGlobals,
      ],
      'no-restricted-properties': [
        'error',
        ...fetchProperties,
        ...networkProperties,
        ...indexedDbProperties,
        ...storageProperties,
      ],
    },
  },
  {
    files: ['src/shared/api-client/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-globals': ['error', indexedDbGlobal, ...storageGlobals],
      'no-restricted-properties': ['error', ...indexedDbProperties, ...storageProperties],
    },
  },
  {
    files: ['src/shared/offline/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-globals': ['error', fetchGlobal, ...networkGlobals, ...storageGlobals],
      'no-restricted-properties': [
        'error',
        ...fetchProperties,
        ...networkProperties,
        ...storageProperties,
      ],
    },
  },
  {
    files: ['*.config.{js,ts}', 'tests/**/*.ts', '.dependency-cruiser.cjs'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: ['tests/**/*.{ts,tsx}'],
    rules: { 'security/detect-object-injection': 'off' },
  },
  prettier,
);
