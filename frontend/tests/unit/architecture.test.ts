import { cruise } from 'dependency-cruiser';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const ruleSet = require('../../.dependency-cruiser.cjs');

// Paths are relative to the project root (vitest cwd). `validate: true` is required for rules to apply.
async function violations(target: string) {
  const result = await cruise([target], { validate: true, ruleSet });
  if (typeof result.output === 'string') throw new Error('unexpected output');
  return result.output.summary.violations.map((v) => v.rule.name);
}

describe('architecture (imports)', () => {
  it('src respects app -> features -> shared', async () => {
    expect(await violations('src')).toEqual([]);
  });

  // Each negative fixture proves its rule is live (a rule that never fires protects nothing).
  it.each([
    ['feature-not-import-other-feature', 'arch-violation'],
    ['feature-not-import-other-feature', 'arch-type-only'], // `import type` counts
    ['feature-not-import-app', 'arch-feature-app'],
    ['shared-not-import-features-or-app', 'arch-shared-feature'],
    ['shared-not-import-features-or-app', 'arch-shared-app'],
    ['no-circular', 'arch-cycle'],
    ['not-to-unresolvable', 'arch-unresolvable'],
    ['not-to-dev-dep', 'arch-dev-dep'],
  ])('detects %s (fixture %s)', async (rule, fixture) => {
    expect(await violations(`tests/fixtures/${fixture}/src`)).toContain(rule);
  });
});
