"""Who gets served when there is not enough to go round.

This is the decision nobody had built. Everything else in the system asks how
to close a gap; this asks what to do while the gap is open. A plant short of
one component cannot serve every customer order on time, and somebody has to
choose. Done badly it is whoever shouts; done by date order it is whoever
happened to order first, which is not the same as whoever costs most to miss.

So orders are served in order of what missing them costs per unit of the
scarce material, and the result is compared against plain date order so the
choice has a price attached rather than an assertion.

No AI in here. It is a day-by-day walk of a stock pool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence


@dataclass
class Order:
    """A customer order, expressed in the scarce material it consumes."""
    id: str
    customer: str
    finished_good: str
    due: date
    qty: float                 # of the scarce material, not of the finished good
    amount_idr: float
    pct_per_day: float
    cap_pct: float

    @property
    def exposure_per_unit(self) -> float:
        """Rupiah of penalty per day, per unit of the scarce material.

        Per unit matters: a large order with a soft penalty can be worth
        delaying to protect two small ones with hard penalties, and a ranking
        on total value alone cannot see that.
        """
        if self.qty <= 0:
            return 0.0
        return self.amount_idr * self.pct_per_day / 100.0 / self.qty

    def penalty(self, days_late: int) -> int:
        if days_late <= 0:
            return 0
        pct = min(days_late * self.pct_per_day, self.cap_pct)
        return int(round(self.amount_idr * pct / 100.0))


@dataclass
class Served:
    order: Order
    on: Optional[date]
    days_late: int
    penalty_idr: int
    short_qty: float = 0.0

    def as_dict(self) -> dict:
        return {
            "sales_order": self.order.id, "customer": self.order.customer,
            "finished_good": self.order.finished_good,
            "due": self.order.due.isoformat(),
            "qty": round(self.order.qty, 1),
            "served_on": self.on.isoformat() if self.on else None,
            "days_late": self.days_late,
            "penalty_idr": self.penalty_idr,
            "short_qty": round(self.short_qty, 1),
            "exposure_per_unit": round(self.order.exposure_per_unit, 1),
        }


@dataclass
class Plan:
    rule: str
    served: List[Served] = field(default_factory=list)
    penalty_idr: int = 0
    on_time: int = 0
    late: int = 0
    unserved: int = 0

    def as_dict(self) -> dict:
        return {"rule": self.rule, "penalty_idr": self.penalty_idr,
                "on_time": self.on_time, "late": self.late,
                "unserved": self.unserved,
                "orders": [s.as_dict() for s in self.served]}


def _assign(orders: Sequence[Order], opening: float,
            arrivals: Dict[date, float], start: date, horizon_days: int,
            key, rule: str) -> Plan:
    """Serve the whole order book in `key` order, earliest supply first.

    Priority is applied across the whole horizon rather than day by day. A
    day-by-day queue cannot hold stock back for a high-penalty order that
    falls due next week: the order is not in the queue yet, so today's order
    takes the stock and the choice is never actually made. Allocation is
    exactly the decision that needs to look ahead.
    """
    # Supply as dated buckets. Opening stock is simply the bucket at `start`.
    buckets: List[List] = [[start, float(opening)]]
    buckets += [[d, float(q)] for d, q in sorted(arrivals.items())
                if d <= start + timedelta(days=horizon_days)]
    buckets.sort(key=lambda b: b[0])

    horizon_end = start + timedelta(days=horizon_days)
    done: List[Served] = []

    for o in sorted(orders, key=key):
        # A partial shipment is not modelled: an assembly line needs the whole
        # kit or it does not run, so an order is served in full or it waits.
        if sum(b[1] for b in buckets) + 1e-9 < o.qty:
            late = (horizon_end - o.due).days
            done.append(Served(o, None, late, o.penalty(late), short_qty=o.qty))
            continue

        need, last = o.qty, start
        for b in buckets:
            if need <= 1e-9:
                break
            if b[1] <= 0:
                continue
            take = min(b[1], need)
            b[1] -= take
            need -= take
            last = b[0]

        # Supply that arrived before the order was due does not make it early.
        on = max(o.due, last)
        late = (on - o.due).days
        done.append(Served(o, on, late, o.penalty(late)))

    done.sort(key=lambda s: (s.order.due, s.order.id))
    return Plan(rule, done,
                penalty_idr=sum(s.penalty_idr for s in done),
                on_time=sum(1 for s in done if s.on and s.days_late <= 0),
                late=sum(1 for s in done if s.on and s.days_late > 0),
                unserved=sum(1 for s in done if s.on is None))


def allocate(orders: Sequence[Order], opening: float,
             arrivals: Dict[date, float], start: date,
             horizon_days: int = 120) -> dict:
    """The proposed allocation, and what date order would have cost instead."""
    if not orders:
        return {"feasible": True, "proposed": None, "by_date": None,
                "saving_idr": 0,
                "reason": "no customer orders consume this material"}

    by_exposure = _assign(orders, opening, arrivals, start, horizon_days,
                          key=lambda o: (-o.exposure_per_unit, o.due, o.id),
                          rule="highest penalty per unit first")
    by_date = _assign(orders, opening, arrivals, start, horizon_days,
                      key=lambda o: (o.due, o.id),
                      rule="earliest due date first")

    # Date order is the honest comparison, because it is what happens when
    # nobody decides. If it wins, say so: a ranking that costs more than
    # doing the obvious thing is not worth the argument it starts.
    best = min((by_exposure, by_date), key=lambda p: p.penalty_idr)
    return {
        "feasible": best.penalty_idr == 0,
        "proposed": best.as_dict(),
        "by_date": by_date.as_dict(),
        "saving_idr": by_date.penalty_idr - best.penalty_idr,
        "reason": (f"{best.rule}: Rp {best.penalty_idr:,} in penalties, "
                   f"{best.on_time} on time, {best.late} late, "
                   f"{best.unserved} unserved"),
    }


def demo() -> None:
    start = date(2026, 9, 4)

    # Three orders, not enough stock for all of them on time. The big order is
    # soft (0.1%/day), the two small ones are hard (1.0%/day): serving in date
    # order protects the wrong one.
    orders = [
        Order("SO-BIG", "Soft Customer", "FG-1", date(2026, 9, 6), 40.0,
              2_000_000_000, 0.1, 10.0),
        Order("SO-A", "Hard Customer A", "FG-2", date(2026, 9, 8), 20.0,
              400_000_000, 1.0, 10.0),
        Order("SO-B", "Hard Customer B", "FG-3", date(2026, 9, 9), 20.0,
              400_000_000, 1.0, 10.0),
    ]
    arrivals = {date(2026, 9, 20): 80.0}

    out = allocate(orders, opening=40.0, arrivals=arrivals, start=start)
    assert not out["feasible"], out["reason"]
    assert out["saving_idr"] > 0, out
    prop = {o["sales_order"]: o for o in out["proposed"]["orders"]}
    dated = {o["sales_order"]: o for o in out["by_date"]["orders"]}

    # Date order spends the 40 units on the big soft order and leaves both
    # hard ones waiting for the 20 September arrival.
    assert dated["SO-BIG"]["days_late"] == 0, dated["SO-BIG"]
    assert dated["SO-A"]["days_late"] > 0 and dated["SO-B"]["days_late"] > 0
    # The proposal protects the two hard orders instead.
    assert prop["SO-A"]["days_late"] == 0 and prop["SO-B"]["days_late"] == 0, prop
    assert prop["SO-BIG"]["days_late"] > 0

    print(f"  by date order    → Rp {out['by_date']['penalty_idr']:,} "
          f"({out['by_date']['on_time']} on time, {out['by_date']['late']} late)")
    print(f"  proposed         → Rp {out['proposed']['penalty_idr']:,} "
          f"({out['proposed']['on_time']} on time, {out['proposed']['late']} late)")
    print(f"  choosing saves   → Rp {out['saving_idr']:,} on the same stock ✓")

    # Enough stock for everyone means no choice to make, and no claimed saving.
    plenty = allocate(orders, opening=500.0, arrivals={}, start=start)
    assert plenty["feasible"] and plenty["saving_idr"] == 0, plenty
    assert plenty["proposed"]["late"] == 0
    print("  enough for all   → feasible, no ranking claimed ✓")

    # An order nothing can reach inside the horizon is reported unserved, with
    # its shortfall, rather than silently dropped.
    never = allocate([orders[0]], opening=0.0, arrivals={}, start=start)
    row = never["proposed"]["orders"][0]
    assert row["served_on"] is None and row["short_qty"] == 40.0, row
    assert never["proposed"]["unserved"] == 1
    print("  unreachable      → reported unserved with its shortfall ✓")

    # The cap holds here too: a year late is 10%, not 36%.
    stuck = allocate([Order("SO-C", "X", "FG-9", date(2026, 9, 5), 10.0,
                            1_000_000_000, 0.5, 10.0)],
                     opening=0.0, arrivals={}, start=start, horizon_days=365)
    assert stuck["proposed"]["penalty_idr"] == 100_000_000, stuck["proposed"]
    print("  penalty cap      → holds in allocation too ✓")

    assert allocate([], 0.0, {}, start)["feasible"]
    print("allocate ok")


if __name__ == "__main__":
    demo()
