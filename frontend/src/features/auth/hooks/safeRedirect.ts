// Control characters (tab, CR, LF, NUL...) and DEL: browsers strip some of them from URLs, which
// can turn "/\t/evil.example" into "//evil.example".
function hasControlChars(value: string): boolean {
  return [...value].some((char) => {
    const code = char.charCodeAt(0);
    return code < 0x20 || code === 0x7f;
  });
}

/** Only same-app paths are accepted as post-login destinations (no open redirect). */
export function safeRedirect(from: unknown): string {
  if (typeof from !== 'string') return '/';
  if (hasControlChars(from) || /\s/.test(from)) return '/';
  if (!from.startsWith('/') || from.startsWith('//') || from.includes('\\')) return '/';
  if (from === '/login') return '/';
  return from;
}
