const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const UNITS: { unit: Intl.RelativeTimeFormatUnit; seconds: number }[] = [
  { unit: "year", seconds: 60 * 60 * 24 * 365 },
  { unit: "month", seconds: 60 * 60 * 24 * 30 },
  { unit: "week", seconds: 60 * 60 * 24 * 7 },
  { unit: "day", seconds: 60 * 60 * 24 },
  { unit: "hour", seconds: 60 * 60 },
  { unit: "minute", seconds: 60 },
  { unit: "second", seconds: 1 },
];

/** e.g. "3 days ago", "yesterday", "just now" */
export function formatTimeAgo(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";

  const deltaSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(deltaSeconds);

  for (const { unit, seconds } of UNITS) {
    if (abs >= seconds || unit === "second") {
      const amount = Math.round(deltaSeconds / seconds);
      if (unit === "second" && abs < 45) return "just now";
      return rtf.format(amount, unit);
    }
  }

  return "just now";
}

/** e.g. "Updated 3 days ago" */
export function formatLabeledAgo(value: string | Date, label: string): string {
  return `${label} ${formatTimeAgo(value)}`;
}

/** Full locale string for tooltips / screen readers. */
export function formatAbsoluteDateTime(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}
