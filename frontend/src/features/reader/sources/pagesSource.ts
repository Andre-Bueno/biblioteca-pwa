import type { LocatorCodec, ReaderSource } from './types';

function clampPage(page: number, pageCount: number): number {
  if (!Number.isFinite(page) || pageCount <= 0) return 0;
  return Math.min(pageCount - 1, Math.max(0, Math.trunc(page)));
}

/** Locator of an image item is the 0-based page index; there is no offset inside a page. */
export const pagesCodec: LocatorCodec = {
  decode(locator) {
    if (locator === null || !Number.isFinite(locator) || locator < 0) return { unit: 0, bp: 0 };
    return { unit: Math.trunc(locator), bp: 0 };
  },
  encode(unit) {
    return Number.isFinite(unit) ? Math.max(0, Math.trunc(unit)) : 0;
  },
  percent(unit, _bp, unitCount) {
    if (unitCount <= 0) return 0;
    const value = ((clampPage(unit, unitCount) + 1) / unitCount) * 100;
    return Math.min(100, Math.max(0, Math.round(value)));
  },
};

/** Manga, PDF, CBZ and folders: one image per page. */
export function createImagePagesSource(pageCount: number): ReaderSource {
  const unitCount = Number.isFinite(pageCount) ? Math.max(0, Math.trunc(pageCount)) : 0;
  return {
    kind: 'pages',
    unitCount,
    codec: pagesCodec,
    capabilities: {
      textSettings: false,
      zoomToggle: true,
      edgeTapsStep: true,
      honorsDirection: true,
    },
    clampUnit: (unit) => clampPage(unit, unitCount),
    unitTitle: (unit) => `Página ${clampPage(unit, unitCount) + 1}`,
  };
}
