import type { ItemType } from '../items';

/** What a series holds: only manga chapters, only books, or both. */
export type SeriesKind = 'manga' | 'book' | 'mixed';

export type MetadataState = 'none' | 'matched' | 'manual' | 'not_found';
export type DescriptionLang = 'pt-br' | 'pt' | 'en' | null;

export type DescriptionOrigin = 'source' | 'translated' | 'manual' | null;

export interface DescriptionSource {
  name: string;
  url: string | null;
}

export interface MetadataCandidate {
  provider: string;
  external_id: string;
  title: string;
  year: number | null;
  description: string;
  cover_available: boolean;
  url: string | null;
}

export type EnrichState = 'idle' | 'running' | 'finished' | 'failed';

export interface EnrichStatus {
  state: EnrichState;
  matched: number;
  not_found: number;
  skipped: number;
  errors: number;
}

export interface SeriesSummary {
  id: string;
  title: string;
  chapter_count: number;
  /** Absent on older servers (then it reads as manga: "capítulos"). */
  kind?: SeriesKind;
  has_cover: boolean;
  description: string | null;
  description_lang: DescriptionLang;
  metadata_state: MetadataState;
  progress: { read_chapters: number; last_item_id: string | null };
}

export interface SeriesList {
  items: SeriesSummary[];
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ChapterProgress {
  locator: number;
  /** 0 to 100. */
  percent: number;
  finished: boolean;
}

export interface Chapter {
  id: string;
  title: string;
  number: number | null;
  page_count: number | null;
  /** Present when the server tells books from manga; absent on older servers. */
  type?: ItemType;
  progress: ChapterProgress | null;
}

export interface SeriesDetail {
  id: string;
  title: string;
  description: string | null;
  description_lang: DescriptionLang;
  /** Optional: absent on older servers (behaves as before). */
  description_origin?: DescriptionOrigin;
  /** For a translated text this is the source of the ORIGINAL (English) text. */
  description_source?: DescriptionSource | null;
  source: { name: string; url: string | null } | null;
  metadata_state: MetadataState;
  chapter_count: number;
  /** Absent on older servers: derived from the chapters (see `seriesKindOf`). */
  kind?: SeriesKind;
  has_cover: boolean;
  chapters: Chapter[];
  continue: { item_id: string; locator: number } | null;
}

/** Links to the source are only rendered for https URLs (never javascript:, data:, http:). */
export function safeHttpsUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

/** A volume (EPUB) is not counted in pages: it is labelled "Livro" and shows progress in %. */
export function isBookChapter(chapter: Pick<Chapter, 'type' | 'page_count'>): boolean {
  if (chapter.type !== undefined) return chapter.type === 'book';
  return !chapter.page_count; // older servers: no page count means not a manga
}

/** The server's `kind` wins; older servers send none, so it is derived from the chapters. */
export function seriesKindOf(series: Pick<SeriesDetail, 'kind' | 'chapters'>): SeriesKind {
  if (series.kind) return series.kind;
  const books = series.chapters.filter(isBookChapter).length;
  if (series.chapters.length > 0 && books === series.chapters.length) return 'book';
  return books > 0 ? 'mixed' : 'manga';
}

/** "3 livros" / "3 itens" / "3 capítulos" (manga, and servers that send no `kind`). */
export function seriesCountLabel(count: number, kind: SeriesKind | undefined): string {
  if (kind === 'book') return count === 1 ? '1 livro' : `${count} livros`;
  if (kind === 'mixed') return count === 1 ? '1 item' : `${count} itens`;
  return count === 1 ? '1 capítulo' : `${count} capítulos`;
}

/** Neighbours of a chapter in the order the server sent. */
export function chapterNeighbours(
  chapters: Chapter[],
  itemId: string,
): { previous: Chapter | null; next: Chapter | null } {
  const index = chapters.findIndex((chapter) => chapter.id === itemId);
  if (index < 0) return { previous: null, next: null };
  return { previous: chapters[index - 1] ?? null, next: chapters[index + 1] ?? null };
}
