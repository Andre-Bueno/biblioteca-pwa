/** `pages`: one image per unit (manga, PDF). `chapters`: one HTML chapter per unit (books). */
export type SourceKind = 'pages' | 'chapters';

/** A reading position: a unit (page or chapter) and the offset inside it, in basis points. */
export interface UnitPosition {
  unit: number;
  bp: number;
}

/** Converts between the saved locator number and a position. Never throws on hostile input. */
export interface LocatorCodec {
  decode(locator: number | null): UnitPosition;
  encode(unit: number, bp: number): number;
  /** Whole-item percent, 0 to 100. */
  percent(unit: number, bp: number, unitCount: number): number;
}

export interface TocItem {
  title: string;
  unit: number;
  anchor: string | null;
}

export interface SourceCapabilities {
  /** Font size and theme apply (text content only). */
  textSettings: boolean;
  /** The "zoom" toggle makes sense. */
  zoomToggle: boolean;
  /** Taps on the screen edges turn the unit. */
  edgeTapsStep: boolean;
  /** The reading direction (rtl/ltr) is honored. */
  honorsDirection: boolean;
}

/** Strategy that hides how each format maps units, locators and capabilities. Pure: no React. */
export interface ReaderSource {
  readonly kind: SourceKind;
  readonly unitCount: number;
  readonly codec: LocatorCodec;
  readonly toc?: readonly TocItem[];
  readonly capabilities: SourceCapabilities;
  /** Keeps a unit index inside `[0, unitCount - 1]` (0 when there are no units). */
  clampUnit(unit: number): number;
  unitTitle(unit: number): string;
}
