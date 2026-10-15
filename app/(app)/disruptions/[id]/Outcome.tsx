"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";

/* Closing the loop.
 *
 * The record used to stop at "sent", so the system knew what it decided and
 * never whether it worked. Otto reads these back as precedent, which is the
 * only reason the next incident can be told "we tried this and it arrived
 * three days late anyway". Without a button, that memory stays empty.
 *
 * Written once, deliberately: a correction is a new reading of reality, not an
 * edit of the first, so the server refuses a second write and the form goes
 * away once an outcome exists. */
const OUTCOMES = [
  { value: "delivered", label: "Delivered" },
  { value: "late", label: "Late" },
  { value: "short", label: "Short" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
] as const;

export default function Outcome({ actionId }: { actionId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<string>("");
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send() {
    if (!choice) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/sigap/actions/${actionId}/outcome`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ outcome: choice, detail: detail.trim() || undefined }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error ?? "failed");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="mt-4 border-t pt-3">
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          Record what happened
        </Button>
        <p className="text-muted-foreground mt-2 text-[11px]">
          The next incident reads this back as precedent.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-3 border-t pt-3">
      <div className="flex flex-wrap gap-2">
        {OUTCOMES.map((o) => (
          <Button
            key={o.value}
            size="sm"
            variant={choice === o.value ? "default" : "outline"}
            onClick={() => setChoice(o.value)}
            disabled={busy}
          >
            {o.label}
          </Button>
        ))}
      </div>

      <label className="block">
        <span className="text-muted-foreground text-[11px]">
          What was actually seen: real arrival date, real quantity, real cost
        </span>
        <textarea
          value={detail}
          onChange={(e) => setDetail(e.target.value)}
          disabled={busy}
          rows={2}
          className="border-input bg-background mt-1 w-full rounded-md border px-3 py-2 text-sm"
          placeholder="Arrived 3 days after the promised date, 78 t of 85 t"
        />
      </label>

      <div className="flex items-center gap-2">
        <Button size="sm" onClick={send} disabled={busy || !choice}>
          {busy ? "Recording…" : "Record"}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)} disabled={busy}>
          Cancel
        </Button>
      </div>

      {error && <p className="font-mono text-xs text-rose-700 dark:text-rose-400">{error}</p>}
    </div>
  );
}
