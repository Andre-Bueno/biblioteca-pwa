// @vitest-environment node
import { ESLint } from 'eslint';
import { describe, expect, it } from 'vitest';

const eslint = new ESLint();

async function messages(code: string, filePath: string) {
  const [result] = await eslint.lintText(code, { filePath });
  return result!.messages.map((m) => `${m.ruleId}: ${m.message}`).join('\n');
}

const feature = 'src/features/library/x.ts';
const forbidden: [string, string, string][] = [
  ['bare fetch', 'void fetch("/a");', 'raw fetch'],
  ['window.fetch', 'void window.fetch("/a");', 'raw fetch'],
  ['globalThis.fetch', 'void globalThis.fetch("/a");', 'raw fetch'],
  ['self.fetch', 'void self.fetch("/a");', 'raw fetch'],
  ['window["fetch"]', 'void window["fetch"]("/a");', 'raw fetch'],
  ['bare localStorage', 'localStorage.setItem("a", "b");', 'web storage'],
  ['window.localStorage', 'window.localStorage.setItem("a", "b");', 'web storage'],
  ['globalThis.localStorage', 'globalThis.localStorage.setItem("a", "b");', 'web storage'],
  ['bare sessionStorage', 'sessionStorage.setItem("a", "b");', 'web storage'],
  ['window.sessionStorage', 'window.sessionStorage.setItem("a", "b");', 'web storage'],
  ['globalThis.sessionStorage', 'globalThis.sessionStorage.setItem("a", "b");', 'web storage'],
  ['bare XMLHttpRequest', 'void new XMLHttpRequest();', 'api-client'],
  ['window.XMLHttpRequest', 'void new window.XMLHttpRequest();', 'api-client'],
  ['bare WebSocket', 'void new WebSocket("ws://a");', 'api-client'],
  ['globalThis.WebSocket', 'void new globalThis.WebSocket("ws://a");', 'api-client'],
  ['navigator.sendBeacon', 'navigator.sendBeacon("/a");', 'api-client'],
  ['bare indexedDB', 'void indexedDB.open("a");', 'indexedDB'],
  ['window.indexedDB', 'void window.indexedDB.open("a");', 'indexedDB'],
];

describe('eslint restricted globals', () => {
  it.each(forbidden)('flags %s in a feature', async (_name, code, expected) => {
    expect(await messages(code, feature)).toContain(expected);
  });

  it('allows fetch inside shared/api-client', async () => {
    expect(
      await messages('void window.fetch("/a"); void fetch("/b");', 'src/shared/api-client/x.ts'),
    ).not.toContain('raw fetch');
  });

  it('allows XHR/WebSocket/sendBeacon inside shared/api-client but not indexedDB', async () => {
    const out = await messages(
      'void new XMLHttpRequest(); void new WebSocket("ws://a"); navigator.sendBeacon("/a"); void indexedDB.open("a");',
      'src/shared/api-client/x.ts',
    );
    expect(out).not.toContain('api-client');
    expect(out).toContain('indexedDB');
  });

  it('allows indexedDB inside shared/offline but still bans raw network access', async () => {
    const out = await messages(
      'void indexedDB.open("a"); void fetch("/a"); void new WebSocket("ws://a");',
      'src/shared/offline/x.ts',
    );
    expect(out).not.toContain('indexedDB');
    expect(out).toContain('raw fetch');
    expect(out).toContain('api-client');
  });

  it('still bans web storage inside shared/api-client', async () => {
    expect(
      await messages('window.localStorage.getItem("a");', 'src/shared/api-client/x.ts'),
    ).toContain('web storage');
  });
});
