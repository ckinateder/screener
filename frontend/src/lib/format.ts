export function formatPrice(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  return value.toFixed(abs !== 0 && abs < 1 ? 4 : 2);
}

export function formatChange(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  // Always 2dp: a $0.49 move on a $225 stock should read +0.49, not +0.4900.
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

export function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function formatVolume(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const units: [number, string][] = [
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ];
  for (const [size, suffix] of units) {
    if (Math.abs(value) >= size) return `${(value / size).toFixed(2)}${suffix}`;
  }
  return String(Math.round(value));
}

/** Tailwind text colour class for a signed change. */
export function changeClass(value: number | null | undefined): string {
  if (!value) return "text-muted";
  return value > 0 ? "text-up" : "text-down";
}
