import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync('src/shared/theme/theme.css', 'utf8');

describe('theme.css tokens', () => {
  it('declares each dark value exactly once', () => {
    for (const dark of [
      '#121316',
      '#1c1e23',
      '#eceef2',
      '#9aa1ad',
      '#2f333b',
      '#34d399',
      '#0b0c0f',
    ]) {
      expect(css.split(dark)).toHaveLength(2);
    }
  });

  it('keeps both dark triggers (explicit data-theme and system preference)', () => {
    expect(css).toMatch(/prefers-color-scheme:\s*dark\)\s*{\s*:root:not\(\[data-theme\]\)/);
    expect(css).toContain(":root[data-theme='dark']");
    expect(css.match(/--if-dark:\s*initial;/g)).toHaveLength(2);
  });

  it('defines every color token in :root', () => {
    for (const name of [
      'bg',
      'surface',
      'text',
      'text-muted',
      'border',
      'accent',
      'accent-contrast',
      'danger',
      'success',
    ]) {
      expect(css).toContain(`--color-${name}:`);
    }
  });
});
