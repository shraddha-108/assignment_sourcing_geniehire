export const BANDS = [
  { key: "entry", label: "Entry", min: 0, max: 2 },
  { key: "mid", label: "Mid", min: 3, max: 7 },
  { key: "senior", label: "Senior", min: 8, max: null },
] as const;

export type SeniorityFilterBand = (typeof BANDS)[number]["key"];

export type ExperienceRange = {
  min: number;
  max: number | null;
};

export function rangeFromSelection(
  selected: readonly SeniorityFilterBand[],
): ExperienceRange | null {
  if (selected.length === 0) return null;

  const indexes = [...new Set(selected)]
    .map((band) => BANDS.findIndex((entry) => entry.key === band))
    .sort((left, right) => left - right);

  if (
    indexes.some((index) => index < 0) ||
    indexes.at(-1)! - indexes[0] + 1 !== indexes.length
  ) {
    return null;
  }

  const firstBand = BANDS[indexes[0]];
  const lastBand = BANDS[indexes.at(-1)!];
  return { min: firstBand.min, max: lastBand.max };
}

export function selectionFromRange(
  min: number | null,
  max: number | null,
): SeniorityFilterBand[] {
  return BANDS.flatMap((firstBand, startIndex) => {
    for (let endIndex = startIndex; endIndex < BANDS.length; endIndex += 1) {
      const lastBand = BANDS[endIndex];
      if (firstBand.min === min && lastBand.max === max) {
        return BANDS.slice(startIndex, endIndex + 1).map((band) => band.key);
      }
    }
    return [];
  });
}
