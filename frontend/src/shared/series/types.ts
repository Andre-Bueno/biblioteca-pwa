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

/** Neighbours of a chapter in the order the server sent. */
export function chapterNeighbours(
  chapters: Chapter[],
  itemId: string,
): { previous: Chapter | null; next: Chapter | null } {
  const index = chapters.findIndex((chapter) => chapter.id === itemId);
  if (index < 0) return { previous: null, next: null };
  return { previous: chapters[index - 1] ?? null, next: chapters[index + 1] ?? null };
}
