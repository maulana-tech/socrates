"use client";

import { Bars, Figure, type Datum } from "@/components/charts";

/** A chart an agent drew from something on the shared board.
 *
 *  The spec comes from engine/charting.py, which refuses to build one that
 *  would mislead: mixed units on one axis, a text column where a number
 *  belongs, a key nobody read. So this file only draws. It does not decide
 *  what is drawable, and it must not quietly fix a spec it dislikes.
 */
export type FindingChart = {
  kind: "bar" | "line" | "scatter";
  title: string;
  x: string;
  y: string;
  series?: string | null;
  unit?: string | null;
  /** Which end of the data survived the row limit. */
  order?: "highest" | "lowest";
  points: { x: string; y: number; series?: string }[];
  total_rows: number;
  truncated: number;
  note?: string;
  from_key: string;
  origin: string;
  source: string;
};

const fmt = (n: number) =>
  n.toLocaleString("en-US", { maximumFractionDigits: 2 });

/* A line and a scatter are the same picture with the stroke turned off, so
 * they share one path. Kept deliberately plain: no gridlines, no second hue,
 * no legend for a single series. The axis labels are the chart's own columns,
 * so a reader can go back to the table and check it. */
function Plot({ chart }: { chart: FindingChart }) {
  const { points, kind } = chart;
  const ys = points.map((p) => p.y);
  const lo = Math.min(...ys, 0);
  const hi = Math.max(...ys);
  const span = hi - lo || 1;
  const W = 100;
  const H = 42;
  const at = (i: number) =>
    points.length === 1 ? W / 2 : (i / (points.length - 1)) * W;
  const up = (v: number) => H - ((v - lo) / span) * H;

  return (
    <div className="viz">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-32 w-full overflow-visible"
        role="img"
        aria-label={`${chart.title}. ${chart.y} against ${chart.x}.`}
      >
        {kind === "line" && (
          <polyline
            points={points.map((p, i) => `${at(i)},${up(p.y)}`).join(" ")}
            fill="none"
            stroke="currentColor"
            strokeWidth="0.6"
            vectorEffect="non-scaling-stroke"
            className="text-primary"
          />
        )}
        {points.map((p, i) => (
          <circle
            key={`${p.x}-${i}`}
            cx={at(i)}
            cy={up(p.y)}
            r="1.1"
            vectorEffect="non-scaling-stroke"
            className="fill-primary"
          />
        ))}
      </svg>
      <div className="text-muted-foreground mt-2 flex justify-between font-mono text-[10px] tabular-nums">
        <span>{points[0]?.x}</span>
        <span>
          {fmt(lo)} to {fmt(hi)}
          {chart.unit ? ` ${chart.unit}` : ""}
        </span>
        <span>{points[points.length - 1]?.x}</span>
      </div>
    </div>
  );
}

export function FindingChartBlock({ chart }: { chart: FindingChart }) {
  if (!chart.points?.length) return null;

  const unit = chart.unit ? ` ${chart.unit}` : "";
  const data: Datum[] = chart.points.map((p) => ({
    label: p.x,
    sub: p.series ?? undefined,
    value: p.y,
    display: `${fmt(p.y)}${unit}`,
  }));

  return (
    <Figure
      title={chart.title}
      blurb={`${chart.y} by ${chart.x}${
        chart.total_rows ? ` · ${chart.total_rows} rows` : ""
      }`}
      origin={chart.origin}
      source={chart.source}
      note={chart.note || undefined}
      /* The table is not a fallback for a broken chart, it is the chart in a
         form a screen reader and a sceptic can both read. */
      table={{
        head: [chart.x, `${chart.y}${unit}`],
        rows: chart.points.map((p) => [p.x, fmt(p.y)]),
      }}
    >
      {chart.kind === "bar" ? <Bars data={data} /> : <Plot chart={chart} />}
    </Figure>
  );
}

export function FindingCharts({ charts }: { charts?: FindingChart[] | null }) {
  if (!charts?.length) return null;
  return (
    <div className="space-y-3">
      {charts.map((c, i) => (
        <FindingChartBlock key={`${c.from_key}-${i}`} chart={c} />
      ))}
    </div>
  );
}
