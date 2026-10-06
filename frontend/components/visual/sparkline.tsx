import { sparkEnd, sparkPath } from "@/lib/visual";

/** A trend with no axes: the area, the line and a dot on the latest value. The label says what it shows. */
export function Sparkline({ values, label, width = 120, height = 32, className }: {
  values: number[]; label: string; width?: number; height?: number; className?: string;
}) {
  const line = sparkPath(values, width, height);
  const end = sparkEnd(values, width, height);
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"
      width={width} height={height} className={className} style={{ overflow: "visible" }}>
      {line ? <path d={`${line} L${width} ${height} L0 ${height} Z`} fill="var(--primary-container)" stroke="none" /> : null}
      {line ? <path d={line} fill="none" stroke="var(--primary)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" /> : null}
      {end ? <circle cx={end.x} cy={end.y} r={2.5} fill="var(--primary)" /> : null}
    </svg>
  );
}
