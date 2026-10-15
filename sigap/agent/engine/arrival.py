"""When a shipment actually lands.

Three places in this system used to compute a more honest arrival date and all
three were thrown away: Kira added the import permit, Milo added port dwell,
and the qualification days on every option were read by nobody. The costing
engine planned on the raw date from master data, so a plan could be called
safe while the goods landed after the stockout.

This is the one place that answers the question, and everyone calls it. No AI
in here either: it is calendar arithmetic with its reasons attached.

The model, which is a choice and is stated rather than buried:

  booked date
    + the longest of the PRE-SHIPMENT approvals, in working days
    + port dwell, in calendar days
  = effective arrival

Pre-shipment approvals take the longest rather than the sum, because they run
in parallel: an import permit for a new origin country is processed while the
supplier's first article is being approved, not after it. Summing them would
double count. Dwell is added on top and in calendar days, because a container
sits in the yard through the weekend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import FrozenSet, List


def add_working_days(start: date, days: int, skip: FrozenSet[str] = frozenset()) -> date:
    """`days` working days after `start`, skipping weekends and `skip`.

    A permit that takes ten working days does not take ten working days across
    Idul Fitri, and `skip` is where the holiday calendar lands.
    """
    d, left = start, days
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in skip:
            left -= 1
    return d


@dataclass
class Step:
    reason: str
    days: int
    working_days: bool


@dataclass
class Estimate:
    booked: date
    effective: date
    steps: List[Step] = field(default_factory=list)

    @property
    def slip_days(self) -> int:
        return (self.effective - self.booked).days

    def explain(self) -> str:
        """One line a buyer can check, which is the point of carrying steps."""
        if not self.steps:
            return f"{self.booked.isoformat()}, nothing added"
        parts = [f"{s.reason} +{s.days}{'wd' if s.working_days else 'd'}"
                 for s in self.steps]
        return (f"{self.booked.isoformat()} "
                + " ".join(parts)
                + f" = {self.effective.isoformat()} ({self.slip_days}d later)")

    def as_dict(self) -> dict:
        return {
            "booked": self.booked.isoformat(),
            "effective": self.effective.isoformat(),
            "slip_days": self.slip_days,
            "steps": [{"reason": s.reason, "days": s.days,
                       "working_days": s.working_days} for s in self.steps],
            "explain": self.explain(),
        }


def effective_arrival(
    booked: date,
    *,
    permit_days: int = 0,
    permit_reason: str = "import permit",
    qualification_days: int = 0,
    dwell_days: int = 0,
    dwell_reason: str = "port dwell",
    holidays: FrozenSet[str] = frozenset(),
) -> Estimate:
    """The date to plan against, and what moved it.

    Every argument defaults to nothing added, so a caller that knows about one
    correction does not have to pretend to know about the others.
    """
    steps: List[Step] = []
    d = booked

    # Pre-shipment approvals, in parallel. The longest one sets the departure.
    pre = max(permit_days, qualification_days)
    if pre > 0:
        if permit_days >= qualification_days and permit_days > 0:
            steps.append(Step(permit_reason, permit_days, True))
        if qualification_days > 0:
            # Named even when it is not the binding one, because "we also need
            # 5 days of first-article approval" is information a buyer wants
            # whether or not it is on the critical path today.
            steps.append(Step("supplier qualification", qualification_days,
                              True))
        d = add_working_days(d, pre, holidays)

    if dwell_days > 0:
        steps.append(Step(dwell_reason, dwell_days, False))
        d = d + timedelta(days=dwell_days)

    return Estimate(booked, d, steps)


def demo() -> None:
    cal = frozenset({"2027-03-19", "2027-03-29", "2027-03-30"})

    # Nothing to add: the booked date is the answer, and it says so.
    plain = effective_arrival(date(2026, 9, 26))
    assert plain.effective == plain.booked and plain.slip_days == 0
    assert "nothing added" in plain.explain()

    # Working days, not calendar days. 10 working days from a Friday is 14 days.
    permit = effective_arrival(date(2026, 9, 25), permit_days=10)
    assert permit.effective == date(2026, 10, 9), permit.effective
    assert permit.slip_days == 14, permit.slip_days

    # Holidays push it further, in the one direction that empties a plant.
    naive = effective_arrival(date(2027, 3, 5), permit_days=10)
    real = effective_arrival(date(2027, 3, 5), permit_days=10, holidays=cal)
    assert real.effective > naive.effective, (naive.effective, real.effective)

    # Pre-shipment approvals run in parallel: the longest binds, and summing
    # them would double count. This is the assumption worth a test.
    both = effective_arrival(date(2026, 9, 25), permit_days=10,
                             qualification_days=7)
    only = effective_arrival(date(2026, 9, 25), permit_days=10)
    assert both.effective == only.effective, (both.effective, only.effective)
    assert len(both.steps) == 2, "the non-binding approval is still reported"

    # Qualification alone binds when there is no permit.
    qual = effective_arrival(date(2026, 9, 25), qualification_days=7)
    assert qual.effective == date(2026, 10, 6), qual.effective

    # Dwell is calendar days and lands on top of the approvals.
    full = effective_arrival(date(2026, 9, 25), permit_days=10,
                             qualification_days=7, dwell_days=5)
    assert full.effective == date(2026, 10, 14), full.effective
    assert full.slip_days == 19, full.slip_days
    assert [s.reason for s in full.steps][-1] == "port dwell"

    print("  " + full.explain())
    print("  parallel approvals: permit 10wd + qualification 7wd lands with "
          f"the permit alone, {both.effective} either way ✓")
    print("arrival ok")


if __name__ == "__main__":
    demo()
