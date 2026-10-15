import { ShieldAlert, ShieldCheck } from "lucide-react";

/* Why an action went on its own authority, or why it is waiting.
 *
 * Value is only half the test. A transfer under the limit still waits when
 * anything under the decision is modelled or missing, and without this the
 * approver sees a pending action and has no way to find out what held it.
 * The reason is written at the moment the action is raised, so it reflects the
 * evidence as it stood then, not as it stands now. */
export function AutonomyNote({ autonomous, reason }: {
  autonomous: number;
  reason?: string | null;
}) {
  if (!reason) {
    // Older actions predate the column. Say nothing rather than guess.
    return autonomous === 1 ? (
      <span className="text-muted-foreground text-xs">
        ran on its own authority, under the limit
      </span>
    ) : null;
  }

  const alone = autonomous === 1;
  const Icon = alone ? ShieldCheck : ShieldAlert;
  return (
    <span
      className={`inline-flex items-start gap-1.5 text-xs ${
        alone ? "text-muted-foreground" : "text-amber-700 dark:text-amber-500"
      }`}
    >
      <Icon className="mt-px size-3.5 shrink-0" aria-hidden />
      <span>
        {alone ? "Ran on its own authority. " : "Waiting for a person. "}
        {/* The reasons are written as fragments, so they start lower case and
          * would read as "for a person. the figures" after the lead-in. */}
        {reason.charAt(0).toUpperCase() + reason.slice(1)}
      </span>
    </span>
  );
}
