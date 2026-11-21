/** Reader route; `serie` tells the reader which series (and chapter order) the chapter came from. */
export function readerPath(itemId: string, seriesId?: string | null): string {
  const base = `/ler/${encodeURIComponent(itemId)}`;
  return seriesId ? `${base}?serie=${encodeURIComponent(seriesId)}` : base;
}

export function seriesPath(seriesId: string): string {
  return `/serie/${encodeURIComponent(seriesId)}`;
}
