import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { api, idr, type Scorecard, type View } from "@/app/lib";
import { DataTable } from "@/components/data-table";
import { Empty, Fact, Metric, PageHeader, Rail, Section } from "@/components/shell";
import { OriginBadge } from "@/components/status-badge";

export const dynamic = "force-dynamic";

const num = (n: number | null | undefined, unit = "") =>
  n === null || n === undefined
    ? "not known"
    : `${n.toLocaleString("en-US", { maximumFractionDigits: 1 })}${unit}`;

/* This page is the one that is not about an incident. Everything else in the
 * product starts from something going wrong; ordering happens because it is
 * Tuesday. So the ordering review leads, and the measures sit around it. */
export default async function Operate() {
  const [s, work] = await Promise.all([
    api<Scorecard>("data/scorecard"),
    api<View>("data/replenishment"),
  ]);

  if (!s) {
    return (
      <main className="w-full px-4 py-8 md:px-6">
        <PageHeader
          title="Operations"
          lead="The agent service is not responding, so none of these measures can be read."
        />
      </main>
    );
  }

  const { supply, suppliers, governance, risk, data } = s;

  return (
    <main className="w-full px-4 py-4 md:px-6 md:py-8">
      <PageHeader
        title="Operations"
        lead="The standing operation rather than one disruption. Stock is reviewed against
              a reorder point computed from measured demand and measured supplier lead
              time, every day, whether or not anything has gone wrong."
        aside={<OriginBadge origin={supply.origin} source={supply.source} />}
      />

      <Section className="mt-8">
        <div className="grid grid-cols-2 gap-x-6 gap-y-6 md:grid-cols-3 lg:grid-cols-5">
          <Metric
            value={num(supply.at_reorder_point)}
            label="At the reorder point"
            note={`of ${num(supply.positions)} positions${
              supply.at_reorder_point_pct !== null ? `, ${supply.at_reorder_point_pct}%` : ""
            }`}
          />
          <Metric
            value={num(supply.thinnest_cover_days, "d")}
            label="Thinnest cover"
            note={`median ${num(supply.median_cover_days, "d")} across the book`}
          />
          <Metric
            value={num(suppliers.on_time_pct, "%")}
            label="Supplier on time"
            note={`weighted over ${num(suppliers.orders)} orders`}
          />
          <Metric
            value={num(governance.autonomous_pct, "%")}
            label="Decided without a person"
            note={`${num(governance.awaiting_a_person)} awaiting approval now`}
          />
          <Metric
            value={num(data.trusted_pct, "%")}
            label="Answers from a real record"
            note={`${data.trusted} of ${data.entities} entities live or uploaded`}
          />
        </div>
      </Section>

      <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Section
          title="Ordering review"
          note="Position is stock on hand plus supply in transit, less anything already
                promised to another handling. An order is proposed only when that falls
                to the reorder point, so supply already on the water is never ordered twice."
          className="mt-0"
        >
          {work && work.rows && work.rows.length > 0 ? (
            <DataTable
              columns={work.columns ?? []}
              rows={work.rows}
              origin={work.origin ?? "modelled"}
              source={work.source ?? ""}
              note={work.note}
              highlight={(r) => r.status === "order_now"}
            />
          ) : (
            <Empty
              what="Nothing is at its reorder point."
              why="Every position still has more cover than its supplier's lead time needs,
                   so there is nothing to order today."
            />
          )}
        </Section>

        <div className="space-y-6">
          <Rail title="Where the answers come from">
            {Object.entries(data.by_entity).map(([entity, v]) => (
              <Fact
                key={entity}
                label={entity}
                value={v.origin}
                tone={v.trusted ? "plain" : "quiet"}
              />
            ))}
            <Fact
              label="Rule documents"
              value={`${data.rule_documents} · ${data.rule_parameters} parameters`}
            />
            {data.fx_rate && (
              <Fact
                label="USD rate"
                value={`${data.fx_rate.toLocaleString("en-US")} · ${data.fx_as_of}`}
              />
            )}
          </Rail>

          <Rail title="Suppliers">
            <Fact label="On the book" value={num(suppliers.count)} />
            <Fact
              label={`Averaging ${suppliers.slip_threshold_days}+ days late`}
              value={num(suppliers.over_slip_threshold)}
              tone={suppliers.over_slip_threshold > 0 ? "warn" : "plain"}
            />
            {suppliers.worst && <Fact label="Worst slip" value={suppliers.worst} />}
          </Rail>

          <Rail title="Latent risk">
            <Fact label="Findings" value={num(risk.findings)} />
            <Fact
              label="Single sourced"
              value={num(risk.single_sourced)}
              tone={risk.single_sourced > 0 ? "warn" : "plain"}
            />
            {risk.largest_exposure_idr !== null && (
              <Fact label="Largest exposure" value={idr(risk.largest_exposure_idr)} />
            )}
          </Rail>

          {/* The loop, counted. An outcome nobody reads back is a diary entry,
              so the number that matters is how many of them changed a decision. */}
          <Rail title="Learning from outcomes">
            <Fact label="Actions raised" value={num(governance.actions)} />
            <Fact label="Outcomes recorded" value={num(governance.outcomes_recorded)} />
            <Fact
              label="Feeding the planner"
              value={num(governance.outcomes_feeding_the_planner)}
              tone={governance.outcomes_feeding_the_planner > 0 ? "plain" : "quiet"}
            />
          </Rail>

          <Link
            href="/agents/exposure"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-xs"
          >
            Latent risk in full
            <ArrowRight className="size-3" />
          </Link>
        </div>
      </div>

      {supply.unplannable > 0 && (
        <Section
          title="Not planned"
          note={`${supply.unplannable} position(s) have too little withdrawal history to
                 size a cushion from. They are reported rather than given a default,
                 because a cushion sized from a fortnight of data is noise with a
                 decimal point. Upload movement history to bring them in.`}
        >
          <Link
            href="/uploads"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-xs"
          >
            Upload movement history
            <ArrowRight className="size-3" />
          </Link>
        </Section>
      )}
    </main>
  );
}
