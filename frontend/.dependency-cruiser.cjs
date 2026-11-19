/** Architecture rules: app -> features -> shared; a feature never imports another feature. */
module.exports = {
  forbidden: [
    {
      name: 'feature-not-import-other-feature',
      comment: 'Features are isolated; move shared code to src/shared.',
      severity: 'error',
      from: { path: '(?:^|/)src/features/([^/]+)/' },
      to: { path: '(?:^|/)src/features/', pathNot: '(?:^|/)src/features/$1/' },
    },
    {
      name: 'feature-not-import-app',
      severity: 'error',
      from: { path: '(?:^|/)src/features/' },
      to: { path: '(?:^|/)src/app/' },
    },
    {
      name: 'shared-not-import-features-or-app',
      severity: 'error',
      from: { path: '(?:^|/)src/shared/' },
      to: { path: '(?:^|/)src/(features|app)/' },
    },
    {
      name: 'no-circular',
      severity: 'error',
      from: {},
      to: { circular: true },
    },
    {
      name: 'not-to-unresolvable',
      comment: 'Every import must resolve (Vite virtual modules are the only exception).',
      severity: 'error',
      from: {},
      to: { couldNotResolve: true, pathNot: '^virtual:' },
    },
    {
      name: 'not-to-dev-dep',
      comment: 'Runtime code in src must not depend on devDependencies.',
      severity: 'error',
      from: { path: '(?:^|/)src/', pathNot: '\\.d\\.ts$' }, // ambient type references are fine
      to: { dependencyTypes: ['npm-dev'] },
    },
  ],
  options: {
    // Count import type edges too: type-only imports between features still violate isolation.
    tsPreCompilationDeps: true,
    tsConfig: { fileName: 'tsconfig.app.json' },
    doNotFollow: { path: 'node_modules' },
    exclude: { path: '\\.(test|spec)\\.[jt]sx?$' },
  },
};
