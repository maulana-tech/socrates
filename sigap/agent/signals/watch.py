"""The thing that makes "anticipation" more than a word in the name.

`bmkg.poll()` has always been able to find a quake near a plant and raise it.
Nothing ever called it, so every event in the system arrived because a person
posted one. This runs it on a timer inside the API process, which is what the
product claims to do.

Two things it must not do, both learned from what the feed actually returns:

  - Raise the same quake twice. BMKG keeps a quake in its list for hours, so a
    watcher polling every few minutes sees it on every pass. `event_exists`
    settles it against the record rather than against a set in memory, so a
    restart does not re-raise yesterday's news.
  - Die quietly. A feed that is down, slow, or reshaped must cost one skipped
    round, not the watcher. Anything that escapes is caught and reported.

# ponytail: one feed, one thread, fixed interval. A second signal source wants
#           a scheduler rather than a copy of this file.
"""
from __future__ import annotations

import threading
import time
import traceback
from datetime import date
from typing import Callable, List

from core import store
from signals import bmkg

# BMKG publishes on the order of minutes and a quake stays in the list for
# hours, so polling faster buys nothing and just burns the feed's goodwill.
INTERVAL_SECONDS = 300

# Vega is Prevent mode: it looks for risk that has not happened yet. Nothing it
# finds is urgent, so it runs on its own, slower cadence.
EXPOSURE_INTERVAL_SECONDS = 7 * 24 * 3600

# The scan returns dozens of findings. Raising all of them would bury the queue
# it exists to inform, which is the same mistake as re-raising every quake, so
# only the most valuable few become events.
EXPOSURE_TOP_N = 3

# A standing exposure is not news every week. It is news again if it is still
# there a month later and nobody has acted on it.
EXPOSURE_QUIET_DAYS = 30

# Ordering is a daily rhythm, not a reaction. This is the cadence that makes
# the system operate the supply chain rather than only respond to it: nothing
# has to break for the review to happen, the clock is enough.
REPLENISH_INTERVAL_SECONDS = 24 * 3600

# Supplier reliability moves over months, so judging it weekly is already
# generous. It raises a report, never an action.
SUPPLIER_REVIEW_INTERVAL_SECONDS = 7 * 24 * 3600


def sweep(raise_event: Callable[[dict], str]) -> List[str]:
    """One pass. Returns the ids of events actually raised, newest first.

    `raise_event` is injected so the self-check can run the whole path without
    a server: in the service it is the same call POST /events makes.
    """
    out = bmkg.poll()
    if out["origin"] == "missing":
        return []

    raised: List[str] = []
    for hit in out["hits"]:
        body = bmkg.as_event(hit)
        if store.event_exists(body["title"], body["trigger"]):
            continue
        raised.append(raise_event(body))
    return raised


def as_exposure_event(finding: dict) -> dict:
    """One Vega finding, in the shape POST /events expects."""
    where = finding.get("plant") or "-"
    return {
        "kind": "exposure",
        "title": f"{finding['pattern']}: {finding['material']}"[:120],
        # The trigger is the finding's identity, so the same standing risk
        # dedupes against itself while a different one still gets through.
        "trigger": f"Vega: {finding['pattern']} · {finding['material']} · {where}"[:200],
        "payload": finding,
        "source": "tools/exposure.py",
    }


def sweep_exposure(raise_event: Callable[[dict], str]) -> List[str]:
    """One Prevent-mode pass. Raises the few most valuable findings."""
    from core import registry, store
    import tools  # noqa: F401  (registers every tool)

    r = registry.run("scan_supply_exposure", {})
    if not r.value:
        return []

    ranked = sorted(r.value, key=lambda f: f.get("value_idr") or 0, reverse=True)
    raised: List[str] = []
    for finding in ranked[:EXPOSURE_TOP_N]:
        body = as_exposure_event(finding)
        if store.event_exists(body["title"], body["trigger"], within_days=EXPOSURE_QUIET_DAYS):
            continue
        raised.append(raise_event(body))
    return raised


def sweep_replenishment(raise_event: Callable[[dict], str]) -> List[str]:
    """The daily ordering review, raised as one worklist rather than many.

    One event per position would bury the queue, and a buyer does not work
    position by position anyway: they work a list. So the whole review becomes
    one event per day, carrying the positions that need an order.
    """
    from core import registry, rules, store
    import tools  # noqa: F401  (registers every tool)

    r = registry.run("review_replenishment", {})
    if not r.value or not r.value.get("rows"):
        return []

    rows = [x for x in r.value["rows"] if x["status"] == "order_now"]
    if not rows:
        return []

    top = rows[:rules.whole("replenishment_top_n", 12)]
    today = date.today().isoformat()
    body = {
        "kind": "replenishment",
        "title": f"Replenishment review: {len(rows)} position(s) at the reorder point"[:120],
        # The day is the identity, so one review a day gets through and a
        # restart in the afternoon does not raise a second one.
        "trigger": f"Daily replenishment review {today}"[:200],
        "payload": {"positions": top, "order_now": len(rows),
                    "reviewed": r.value.get("reviewed"),
                    "units_to_order": r.value.get("units_to_order"),
                    "not_shown": max(0, len(rows) - len(top)),
                    "origin": r.origin.value, "source": r.source},
        "source": "tools/procurement.py",
    }
    if store.event_exists(body["title"], body["trigger"]):
        return []
    return [raise_event(body)]


def sweep_supplier_review(raise_event: Callable[[dict], str],
                          floor: float = None) -> List[str]:
    """Weekly: suppliers whose own dates have stopped meaning anything.

    `floor` exists so the self-check can exercise the flagging path on a quiet
    book. Tuning the written threshold until a test passes would be the wrong
    way round.
    """
    from core import registry, rules, store
    import tools  # noqa: F401

    r = registry.run("get_supplier_performance", {})
    if not r.value:
        return []

    floor = rules.number("supplier_slip_flag_days", 5.0) if floor is None else floor
    bad = [s for s in r.value
           if float(s.get("avg_slip_days") or 0) >= floor]
    if not bad:
        return []

    bad.sort(key=lambda s: -float(s.get("avg_slip_days") or 0))
    week = date.today().isocalendar()
    body = {
        "kind": "supplier_review",
        "title": f"{len(bad)} supplier(s) averaging {floor:g}+ days late"[:120],
        "trigger": f"Weekly supplier review {week[0]}-W{week[1]:02d}"[:200],
        "payload": {"suppliers": bad[:EXPOSURE_TOP_N * 2], "flagged": len(bad),
                    "threshold_days": floor,
                    "origin": r.origin.value, "source": r.source},
        "source": "tools/procurement.py",
    }
    if store.event_exists(body["title"], body["trigger"]):
        return []
    return [raise_event(body)]


def _loop(name: str, one_pass: Callable[[], List[str]], interval: int) -> None:
    while True:
        try:
            raised = one_pass()
            if raised:
                print(f"  watch: raised {len(raised)} event(s) from {name}", flush=True)
        except Exception:                                            # noqa: BLE001
            # A watcher that dies on a bad response stops watching, and nobody
            # finds out until the demo. Lose the round, keep the thread.
            traceback.print_exc()
        time.sleep(interval)


#: Every cadence the system runs on its own: a name, the pass, and how often.
#: Reacting to what happened is one of four, not the whole job.
def cadences(raise_event: Callable[[dict], str], interval: int,
             exposure_interval: int, replenish_interval: int,
             supplier_interval: int):
    return [
        ("BMKG", lambda: sweep(raise_event), interval),
        ("Vega", lambda: sweep_exposure(raise_event), exposure_interval),
        ("Prita", lambda: sweep_replenishment(raise_event), replenish_interval),
        ("Prita weekly", lambda: sweep_supplier_review(raise_event), supplier_interval),
    ]


def start(raise_event: Callable[[dict], str],
          interval: int = INTERVAL_SECONDS,
          exposure_interval: int = EXPOSURE_INTERVAL_SECONDS,
          replenish_interval: int = REPLENISH_INTERVAL_SECONDS,
          supplier_interval: int = SUPPLIER_REVIEW_INTERVAL_SECONDS,
          ) -> List[threading.Thread]:
    """The clocks the system runs on.

    Two of these react to something: a quake, a standing exposure. The other
    two happen because it is a new day or a new week, which is what operating
    a supply chain actually consists of.
    """
    threads = [threading.Thread(target=_loop, daemon=True, args=c)
               for c in cadences(raise_event, interval, exposure_interval,
                                 replenish_interval, supplier_interval)]
    for t in threads:
        t.start()
    print(f"  watch: BMKG every {interval}s · Vega every {exposure_interval}s"
          f" · replenishment every {replenish_interval}s"
          f" · supplier review every {supplier_interval}s", flush=True)
    return threads


def demo() -> None:
    seen: List[dict] = []

    def fake_raise(body: dict) -> str:
        seen.append(body)
        eid = store.record_event(body["kind"], body["title"], body["trigger"],
                                 body["payload"], body["source"])
        return eid

    first = sweep(fake_raise)
    if not seen:
        # Offline, or a quiet day. Both are real answers, so prove the dedup
        # against a synthetic signal instead of pretending the feed was there.
        body = {"kind": "seismic", "title": "M5.9 quake 48 km from KRW1 plant",
                "trigger": "BMKG: test region, 2026-10-13T00:00:00+00:00",
                "payload": {"facility": "KRW1"}, "source": "watch-check"}
        assert not store.event_exists(body["title"], body["trigger"])
        fake_raise(body)
        assert store.event_exists(body["title"], body["trigger"])
        print("  feed quiet or offline; dedup proven against a synthetic signal ✓")
    else:
        print(f"  first sweep raised {len(first)} event(s) from the live feed")

    # The point of the whole file: a second pass must raise nothing new.
    again = sweep(fake_raise)
    assert again == [], f"the same quakes were raised twice: {again}"
    print("  second sweep raised nothing, so a restart will not replay the feed ✓")

    # Prevent mode. The scan finds dozens; only the few worth a person's
    # attention become events, and a standing risk does not reappear weekly.
    before = len(seen)
    first = sweep_exposure(fake_raise)
    assert len(first) <= EXPOSURE_TOP_N, f"the queue must not be buried: {len(first)}"
    if first:
        ranked = [b["payload"]["value_idr"] for b in seen[before:]]
        assert ranked == sorted(ranked, reverse=True), "the most valuable should go first"
        assert all(b["kind"] == "exposure" for b in seen[before:])
        print(f"  Vega raised the top {len(first)} of the scan, worth "
              f"Rp {ranked[0]:,} at the head")
    assert sweep_exposure(fake_raise) == [], "a standing exposure was raised twice"
    print("  the same standing risk does not come back next pass ✓")

    # The two cadences that run because it is a new day, not because anything
    # broke. This is the difference between responding and operating.
    before = len(seen)
    daily = sweep_replenishment(fake_raise)
    if daily:
        body = seen[-1]
        assert body["kind"] == "replenishment", body
        pos = body["payload"]["positions"]
        assert pos and all(p["status"] == "order_now" for p in pos), pos
        assert len(pos) <= 12, f"the worklist must stay readable: {len(pos)}"
        # Most urgent first, or the cap throws away the wrong ones.
        cover = [p["cover_days"] for p in pos]
        assert cover == sorted(cover), cover
        print(f"  daily review raised {body['payload']['order_now']} position(s) "
              f"needing {body['payload']['units_to_order']:,.0f} units, "
              f"{len(pos)} on the worklist")
    else:
        print("  daily review found nothing at the reorder point today")
    assert sweep_replenishment(fake_raise) == [], \
        "the same day's review was raised twice"

    # Exercise the flagging path explicitly: the real threshold may well find
    # nothing on a healthy book, and a check that proves nothing is worse than
    # no check.
    forced = sweep_supplier_review(fake_raise, floor=0.1)
    assert forced, "no supplier slipped at all, which the fixture should not allow"
    fbody = seen[-1]
    fslips = [float(x["avg_slip_days"]) for x in fbody["payload"]["suppliers"]]
    assert fslips == sorted(fslips, reverse=True) and min(fslips) >= 0.1, fslips
    print(f"  weekly review, forced threshold → {fbody['payload']['flagged']} "
          f"supplier(s), worst averaging {fslips[0]:.1f} days late ✓")

    weekly = sweep_supplier_review(fake_raise)
    if weekly:
        body = seen[-1]
        assert body["kind"] == "supplier_review", body
        slips = [float(x["avg_slip_days"]) for x in body["payload"]["suppliers"]]
        assert slips == sorted(slips, reverse=True), slips
        assert min(slips) >= body["payload"]["threshold_days"], slips
        print(f"  weekly review flagged {body['payload']['flagged']} supplier(s), "
              f"worst averaging {slips[0]:.1f} days late")
    else:
        print("  weekly review flagged no supplier over the threshold")
    assert sweep_supplier_review(fake_raise) == [], \
        "the same week's supplier review was raised twice"

    # All four clocks, and nothing is wired to a clock it does not have.
    names = [c[0] for c in cadences(fake_raise, 1, 2, 3, 4)]
    assert names == ["BMKG", "Vega", "Prita", "Prita weekly"], names
    assert [c[2] for c in cadences(fake_raise, 1, 2, 3, 4)] == [1, 2, 3, 4]
    print(f"  four cadences: {', '.join(names)} ✓")
    print("watch ok")


if __name__ == "__main__":
    from core.config import fixtures_only

    fixtures_only(__file__, "SIGAP_WATCH_CHECK")
    demo()
