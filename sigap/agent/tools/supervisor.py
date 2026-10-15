"""Arya's tools (Team lead).

One way in: a disruption event that is already on the record. Arya does not
invent triggers, she reads what arrived through POST /events.
"""
from __future__ import annotations

import json
from typing import Optional

from core.provenance import Origin, Result
from core.registry import register


@register("detect_disruption", "supervisor",
          "Take a disruption signal from an outside feed. In this application events "
          "arrive via POST /events, so this tool reads what has been recorded.",
          {"event_id": {"type": "string"}}, ["event_id"])
def detect_disruption(event_id: str) -> Result:
    from core import store
    with store.connect() as c:
        r = c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not r:
        return Result(None, Origin.MISSING, "events table")
    return Result({"kind": r["kind"], "title": r["title"], "trigger": r["trigger"],
                   **json.loads(r["payload"])}, Origin.LIVE, r["source"])


#: How long a period report covers when nobody says. A week is the shortest
#: window a weekly rhythm can be read from, and the longest one anybody reads.
DEFAULT_PERIOD_DAYS = 7


@register(
    "summarise_period", "supervisor",
    "The facts for a periodic operations report: what was handled, decided, approved "
    "and confirmed over a window, and separately where the position stands now. "
    "Deterministic, every number counted from the record. Use it to write a weekly or "
    "monthly summary. It gives you the figures; the judgement about what matters is "
    "yours, and you must not invent a number it did not return.",
    {"days": {"type": ["integer", "null"],
              "description": f"how many days back to cover. Default {DEFAULT_PERIOD_DAYS}"}},
)
def summarise_period(days: Optional[int] = None) -> Result:
    from datetime import datetime, timedelta, timezone

    from core import store
    from tools.views import scorecard

    # `days or DEFAULT` would turn a request for 0 days into a week of data
    # labelled as what the caller asked for, which is worse than refusing.
    window = DEFAULT_PERIOD_DAYS if days is None else int(days)
    if window < 1:
        return Result(None, Origin.MISSING, "runs + actions tables",
                      note="a period has to be at least one day")

    until = datetime.now(timezone.utc)
    since = until - timedelta(days=window)
    activity = store.period_activity(since.isoformat(), until.isoformat())

    # Two different questions, kept apart on purpose. "What happened this week"
    # is the period; "what is thin right now" is today. A quiet week over a
    # plant that is running out tomorrow is not a good week, and a report that
    # blends the two cannot say so.
    now = scorecard()

    nothing = (activity["handlings"]["finished"] == 0
               and activity["actions"]["raised"] == 0
               and activity["outcomes"]["recorded"] == 0)

    return Result(
        {
            "days": window,
            "from": since.isoformat(timespec="seconds"),
            "to": until.isoformat(timespec="seconds"),
            "what_happened": activity,
            "where_we_stand": {
                "supply": now["supply"], "suppliers": now["suppliers"],
                "risk": now["risk"], "data": {k: v for k, v in now["data"].items()
                                              if k != "by_entity"},
            },
            "quiet": nothing,
        },
        Origin.DERIVED, "runs + actions + approvals tables, and tools/views.scorecard",
        note=("nothing was handled, raised or confirmed in this window. That is a "
              "real answer about the period and says nothing about the position"
              if nothing else ""),
    )


def demo() -> None:
    from datetime import datetime, timedelta, timezone

    from core import store

    # Two halves, kept apart. Before this the only report in the system was
    # about one handling, and nothing could answer "how did the week go".
    r = summarise_period(30)
    assert r.origin is Origin.DERIVED and r.trusted, r.brief()
    v = r.value
    assert set(v) >= {"days", "from", "to", "what_happened", "where_we_stand", "quiet"}
    assert v["days"] == 30 and v["from"] < v["to"]
    did, now = v["what_happened"], v["where_we_stand"]
    assert set(did) >= {"handlings", "decisions", "actions", "approvals", "outcomes"}
    assert set(now) >= {"supply", "suppliers", "risk", "data"}
    print(f"  {did['handlings']['finished']} handling(s) finished, "
          f"{did['actions']['raised']} action(s) raised, "
          f"{did['outcomes']['recorded']} outcome(s) confirmed in 30 days")
    print(f"  and now: {now['supply']['at_reorder_point']} of "
          f"{now['supply']['positions']} positions at the reorder point")

    # The window has to bite, or the report is not about a period at all.
    narrow = summarise_period(1)
    assert narrow.value["from"] > v["from"], (narrow.value["from"], v["from"])
    assert (narrow.value["what_happened"]["handlings"]["finished"]
            <= did["handlings"]["finished"])

    # A quiet period is a statement about the period, not about the position,
    # and the note has to say which.
    if narrow.value["quiet"]:
        assert "about the period" in narrow.note, narrow.note
        assert narrow.value["where_we_stand"]["supply"]["positions"] > 0, \
            "a quiet window must not empty the position"
        print(f"  a quiet day still reports the position ✓")

    assert summarise_period(0).origin is Origin.MISSING

    # Counted, not estimated: the period figures must agree with the rows they
    # came from rather than being assembled a second way.
    until = datetime.now(timezone.utc)
    raw = store.period_activity((until - timedelta(days=30)).isoformat(),
                                until.isoformat())
    assert raw["handlings"]["finished"] == did["handlings"]["finished"]
    assert raw["actions"]["raised"] == did["actions"]["raised"]
    print("supervisor ok")


if __name__ == "__main__":
    demo()
