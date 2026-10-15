import Link from "next/link";

import { api, idr, type PeriodReport, type Run } from "@/app/lib";
import { Markdown } from "@/components/markdown";
import { Section } from "@/components/shell";
import { StatusBadge } from "@/components/status-badge";

export const dynamic = "force-dynamic";

const WINDOWS = [7, 30, 90];

export default async function ReportList(
  { searchParams }: { searchParams: Promise<{ days?: string }> },
) {
  const asked = Number((await searchParams).days);
  const days = WINDOWS.includes(asked) ? asked : 7;
  const [d, period] = await Promise.all([
    api<{ runs: Run[] }>("runs"),
    api<PeriodReport>(`reports/period/${days}`),
  ]);

  return (
    <main className="w-full px-4 py-4 md:px-6 md:py-8">
      <header className="border-b pb-4 md:pb-5">
        <h1 className="mt-1 text-xl font-semibold tracking-tight md:mt-2 md:text-2xl">Reports</h1>
        <p className="text-muted-foreground mt-1 max-w-3xl text-sm leading-relaxed">
          A report over a period, and one per handling. Every figure in both is counted
          from the record rather than written by a model, so anyone can recompute them.
        </p>
      </header>

      {/* The period report leads, because it is the one somebody reads without
          already knowing which handling they care about. */}
      <Section
        title="Over a period"
        action={
          <div className="flex items-center gap-1">
            {WINDOWS.map((n) => (
              <Link
                key={n}
                href={`/reports?days=${n}`}
                aria-current={n === days ? "page" : undefined}
                className={
                  n === days
                    ? "bg-muted rounded-md px-2.5 py-1 font-mono text-xs"
                    : "text-muted-foreground hover:text-foreground rounded-md px-2.5 py-1 font-mono text-xs"
                }
              >
                {n}d
              </Link>
            ))}
          </div>
        }
      >
        {period ? (
          <div className="max-w-3xl rounded-lg border p-5">
            <Markdown>{period.markdown}</Markdown>
          </div>
        ) : (
          <p className="text-muted-foreground max-w-3xl rounded-lg border border-dashed p-6 text-sm">
            The agent service did not return a period report.
          </p>
        )}
      </Section>

      <Section
        title="One handling at a time"
        note="What happened, how the system reasoned, the actions taken, and who approved them."
      >

      {!d?.runs.length ? (
        <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-sm">
          No handlings to report on yet.
        </p>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
          {d.runs.map((r) => (
            <li key={r.id}>
              <Link
                href={`/reports/${r.id}`}
                className="hover:border-foreground/30 block rounded-lg border p-4 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="min-w-0 font-medium">{r.title}</p>
                  <StatusBadge status={r.status} />
                </div>
                <p className="text-muted-foreground mt-1 text-sm">{r.trigger}</p>
                <p className="text-muted-foreground mt-2 font-mono text-[11px]">
                  {new Date(r.started_at).toLocaleString("en-GB")}
                  {r.token_cost_idr > 0 && ` · ${idr(r.token_cost_idr)}`}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
      </Section>
    </main>
  );
}
