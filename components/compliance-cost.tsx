import { Scale } from "lucide-react";

import { idr } from "@/app/lib";

export type ComplianceCost = {
  idr: number;
  chosen: string;
  chosen_cost_idr: number;
  cheaper_but_blocked: string;
  cheaper_cost_idr: number;
  blocked_by: { id: string; label: string; reason: string }[];
};

/* What obeying the rules cost on this incident.
 *
 * Kira's veto cannot be overturned on price, and that is the point: without a
 * figure beside it the veto reads as an assertion, and the cheaper path it
 * struck out is invisible. The number is not an argument for breaking the rule.
 * It is the rule's price, stated plainly, which is what makes it a decision
 * somebody can defend rather than a line in a policy.
 *
 * It renders nothing when nothing blocked was cheaper. A zero would read as
 * "the rules were free" when the honest answer is that there was no cheaper
 * way to begin with. */
export function ComplianceCostNote({ cost }: { cost?: ComplianceCost | null }) {
  if (!cost?.idr) return null;

  return (
    <div className="mt-4 rounded-lg border border-amber-300/70 bg-amber-50/60 p-4 dark:border-amber-900/60 dark:bg-amber-950/20">
      <div className="flex items-start gap-2.5">
        <Scale className="mt-0.5 size-4 shrink-0 text-amber-700 dark:text-amber-500" aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium">
            Following the rules cost {idr(cost.idr)}
          </p>
          <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
            <span className="font-mono">{cost.chosen}</span> at {idr(cost.chosen_cost_idr)} was
            taken because <span className="font-mono">{cost.cheaper_but_blocked}</span> at{" "}
            {idr(cost.cheaper_cost_idr)} was blocked.
          </p>
          <ul className="mt-2 space-y-1">
            {cost.blocked_by.map((b) => (
              <li key={b.id} className="text-muted-foreground text-xs">
                <span className="font-mono">{b.id}</span> {b.label}: {b.reason}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-2 text-[11px]">
            Price cannot overturn this.
          </p>
        </div>
      </div>
    </div>
  );
}
