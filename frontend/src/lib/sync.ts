/**
 * Index of the last bar whose time is <= `t` (ISO dates compare correctly as strings), or -1.
 * Used to map a hovered date onto the other chart: daily -> the week containing it,
 * weekly (Monday label) -> that Monday or the trading day before it.
 */
export function barAtOrBefore(times: string[], t: string): number {
  let lo = 0;
  let hi = times.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

/** ISO date -> days since epoch (UTC), so dates can be interpolated. */
export function dayNumber(iso: string): number {
  return Date.parse(`${iso}T00:00:00Z`) / 86_400_000;
}

// Average calendar days per bar (~1.4 daily, 7 weekly); used to extrapolate past the data,
// e.g. the empty space right of the last bar.
const spacing = (days: number[]) => (days.length > 1 ? (days[days.length - 1] - days[0]) / (days.length - 1) : 1);

/**
 * Chart X-axis sync works in "fractional days": a logical bar position (bar index, possibly
 * fractional or outside the data) maps to a date by interpolating between bar dates. Mapping one
 * chart's visible edges to dates and back onto the other chart's bars aligns daily and weekly
 * charts exactly, including the whitespace beyond the last bar.
 */
export function logicalToDay(days: number[], logical: number): number | null {
  const n = days.length;
  if (n === 0) return null;
  if (logical <= 0) return days[0] + logical * spacing(days);
  if (logical >= n - 1) return days[n - 1] + (logical - (n - 1)) * spacing(days);
  const i = Math.floor(logical);
  return days[i] + (logical - i) * (days[i + 1] - days[i]);
}

/** Inverse of logicalToDay. */
export function dayToLogical(days: number[], day: number): number | null {
  const n = days.length;
  if (n === 0) return null;
  if (day <= days[0]) return (day - days[0]) / spacing(days);
  if (day >= days[n - 1]) return n - 1 + (day - days[n - 1]) / spacing(days);
  let lo = 0;
  let hi = n - 1; // invariant: days[lo] <= day < days[hi]
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (days[mid] <= day) lo = mid;
    else hi = mid;
  }
  return lo + (day - days[lo]) / (days[hi] - days[lo]);
}
