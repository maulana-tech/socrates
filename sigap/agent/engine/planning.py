"""What to hold and what to order. No AI in here either.

The system used to apply one number to every material: a fourteen day floor,
written in a default argument, with nothing behind it. A material whose daily
use swings 40% and whose supplier is three weeks away needs a different
cushion from one that is steady and local, and fourteen days is wrong for both
in opposite directions.

So the cushion is computed from the two things that actually cause a stockout:
demand moving and the supplier being late. Both are measured from records this
system already holds, and where a record is too thin to measure, that is said
rather than filled in.

    safety stock  = z x sqrt( LT x sigma_demand^2 + demand^2 x sigma_LT^2 )
    reorder point = demand x LT + safety stock

The first term is demand risk over the lead time, the second is lead time risk
at the current demand rate. z comes from the service level in
references/operating-targets.md, so the operations manager sets the cushion by
editing a document, not by asking for a deployment.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class Demand:
    """Daily use, measured. `planned` is what master data claims it is."""
    mean: float
    sigma: float
    days: int
    planned: Optional[float] = None

    @property
    def variability(self) -> float:
        """Sigma as a share of the mean. The number the old floor ignored."""
        return self.sigma / self.mean if self.mean else 0.0

    @property
    def planned_error_pct(self) -> Optional[float]:
        if not self.planned:
            return None
        return (self.mean / self.planned - 1) * 100


@dataclass
class LeadTime:
    mean: float
    sigma: float
    observations: int
    assumed: bool = False
    note: str = ""


@dataclass
class Policy:
    material: str
    plant: str
    safety_stock: float
    reorder_point: float
    order_up_to: float
    demand: Demand
    lead_time: LeadTime
    floor_applied: bool = False
    reasons: List[str] = field(default_factory=list)

    @property
    def safety_days(self) -> float:
        return self.safety_stock / self.demand.mean if self.demand.mean else 0.0

    def as_dict(self) -> dict:
        return {
            "material": self.material, "plant": self.plant,
            "safety_stock": round(self.safety_stock, 1),
            "safety_days": round(self.safety_days, 1),
            "reorder_point": round(self.reorder_point, 1),
            "order_up_to": round(self.order_up_to, 1),
            "demand_per_day": round(self.demand.mean, 2),
            "demand_sigma": round(self.demand.sigma, 2),
            "demand_variability_pct": round(self.demand.variability * 100, 1),
            "demand_days_observed": self.demand.days,
            "planned_per_day": self.demand.planned,
            "planned_error_pct": (round(self.demand.planned_error_pct, 1)
                                  if self.demand.planned_error_pct is not None else None),
            "lead_time_days": round(self.lead_time.mean, 1),
            "lead_time_sigma": round(self.lead_time.sigma, 1),
            "lead_time_observations": self.lead_time.observations,
            "lead_time_assumed": self.lead_time.assumed,
            "floor_applied": self.floor_applied,
            "reasons": self.reasons,
        }


@dataclass
class Requirement:
    material: str
    plant: str
    on_hand: float
    on_order: float
    reserved: float
    position: float
    reorder_point: float
    order_qty: float
    cover_days: Optional[float]
    runs_out_on: Optional[str]
    status: str                      # order_now | watch | ok | no_demand
    reason: str = ""

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        for k in ("on_hand", "on_order", "reserved", "position",
                  "reorder_point", "order_qty"):
            d[k] = round(d[k], 1)
        if d["cover_days"] is not None:
            d["cover_days"] = round(d["cover_days"], 1)
        return d


def demand_stats(series: Sequence[Tuple[date, float]], min_days: int = 30,
                 planned: Optional[float] = None) -> Optional[Demand]:
    """Mean and spread of daily use, or None when the history is too thin.

    Returning None matters: a standard deviation computed from a week of data
    is noise with a decimal point, and a cushion sized from noise is worse
    than one an operator chose on purpose.
    """
    if len(series) < max(2, min_days):
        return None
    qty = [q for _d, q in series]
    return Demand(mean=statistics.fmean(qty),
                  sigma=statistics.stdev(qty) if len(qty) > 1 else 0.0,
                  days=len(qty), planned=planned)


def lead_time_stats(orders: Sequence[dict], default_days: float = 30.0,
                    min_observations: int = 2,
                    observed_days: Sequence[float] = ()) -> LeadTime:
    """How long this supplier actually takes, from its own purchase orders.

    `orders` are rows with an order date and a delivery date. One delivery is
    an anecdote: its spread is zero, which would read as a perfectly reliable
    supplier, so below `min_observations` the written default is used and the
    answer says it was assumed.
    """
    days: List[float] = []
    for o in orders:
        a, b = o.get("PurchaseOrderDate") or o.get("OrderedOn"), \
               o.get("RevisedDeliveryDate") or o.get("DeliveryDate")
        if not a or not b:
            continue
        try:
            n = (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
        except ValueError:
            continue
        if n > 0:
            days.append(float(n))

    # What actually happened outranks what a document promised. These come
    # from deliveries this system proposed and then watched land, and they are
    # what makes the next reorder point different from the last one: record a
    # delivery that ran three weeks over and the cushion behind that supplier
    # widens by itself.
    learned = len([d for d in observed_days if d and d > 0])
    days += [float(d) for d in observed_days if d and d > 0]

    if len(days) < max(1, min_observations):
        return LeadTime(default_days, 0.0, len(days), assumed=True,
                        note=(f"{len(days)} delivered order(s) on record, fewer than "
                              f"{min_observations}. Using the written default of "
                              f"{default_days:g} days with no spread"))
    return LeadTime(statistics.fmean(days),
                    statistics.stdev(days) if len(days) > 1 else 0.0,
                    len(days),
                    note=(f"{learned} of {len(days)} observations are recorded "
                          f"outcomes rather than promised dates" if learned else ""))


def policy(material: str, plant: str, demand: Demand, lead: LeadTime,
           z: float = 1.65, min_cover_days: float = 14.0,
           order_cycle_days: float = 30.0) -> Policy:
    """The cushion and the trigger, with the reasons that produced them."""
    variance = (lead.mean * demand.sigma ** 2
                + (demand.mean ** 2) * (lead.sigma ** 2))
    safety = z * math.sqrt(max(variance, 0.0))
    rop = demand.mean * lead.mean + safety

    reasons = [
        f"demand {demand.mean:.2f}/day, spread {demand.sigma:.2f} "
        f"({demand.variability * 100:.0f}%) over {demand.days} days",
        (f"lead time {lead.mean:.0f} days assumed, {lead.note}" if lead.assumed else
         f"lead time {lead.mean:.0f} days, spread {lead.sigma:.1f} "
         f"over {lead.observations} delivered orders"
         + (f". {lead.note}" if lead.note else "")),
        f"service level multiplier {z:g}",
    ]

    # The old fourteen day floor stays, underneath the calculation rather than
    # instead of it. A formula is not a reason to hold less than two weeks of
    # a part that stops a line.
    floor = demand.mean * min_cover_days
    floor_applied = rop < floor
    if floor_applied:
        reasons.append(f"calculated {rop:.0f} is under the {min_cover_days:g} day "
                       f"floor of {floor:.0f}, floor applied")
        rop = floor

    if demand.planned_error_pct is not None and abs(demand.planned_error_pct) >= 10:
        reasons.append(f"master data says {demand.planned:.2f}/day, measured use is "
                       f"{demand.planned_error_pct:+.0f}% against it")

    return Policy(material, plant, safety, rop,
                  rop + demand.mean * order_cycle_days,
                  demand, lead, floor_applied, reasons)


def net_requirement(pol: Policy, on_hand: float, on_order: float,
                    reserved: float = 0.0,
                    start: Optional[date] = None) -> Requirement:
    """Order or not, how much, and when the shelf empties if nobody acts."""
    position = on_hand + on_order - reserved
    d = pol.demand.mean

    if d <= 0:
        return Requirement(pol.material, pol.plant, on_hand, on_order, reserved,
                           position, pol.reorder_point, 0.0, None, None,
                           "no_demand", "no measured consumption, nothing to plan")

    cover = position / d
    runs_out = ((start or date.today()) + timedelta(days=int(cover))).isoformat()

    if position <= pol.reorder_point:
        qty = max(0.0, pol.order_up_to - position)
        status, reason = "order_now", (
            f"position {position:.0f} is at or below the reorder point "
            f"{pol.reorder_point:.0f}, {cover:.0f} days of cover left")
    elif position <= pol.reorder_point * 1.15:
        status, qty = "watch", 0.0
        reason = (f"position {position:.0f} is within 15% of the reorder point "
                  f"{pol.reorder_point:.0f}")
    else:
        status, qty = "ok", 0.0
        reason = f"{cover:.0f} days of cover against a {pol.lead_time.mean:.0f} day lead time"

    return Requirement(pol.material, pol.plant, on_hand, on_order, reserved,
                       position, pol.reorder_point, qty, cover, runs_out,
                       status, reason)


def demo() -> None:
    import collections
    import json
    import pathlib

    here = pathlib.Path(__file__).resolve().parent.parent
    hist = json.loads((here / "fixtures" / "consumption_history.json").read_text())
    fx = json.loads((here / "fixtures" / "ningbo_scenario.json").read_text())

    series: Dict[tuple, list] = collections.defaultdict(list)
    for h in hist:
        series[(h["Material"], h["Plant"])].append(
            (date.fromisoformat(h["Date"]), float(h["Quantity"])))

    stock = {(r["Material"], r["Plant"]): r for r in fx["MaterialStock"]}
    key = ("M-4471", "KRW1")
    row = stock[key]

    # --- demand, measured rather than copied out of master data -----------
    dm = demand_stats(sorted(series[key]), 30, float(row["DailyConsumption"]))
    assert dm is not None and dm.days == 120, dm
    assert dm.sigma > 0, "a flat series would make the whole exercise pointless"
    print(f"  demand           → {dm.mean:.2f}/day, spread {dm.sigma:.2f} "
          f"({dm.variability * 100:.0f}%) over {dm.days} days")

    # Too little history must return nothing, not a confident number.
    assert demand_stats(sorted(series[key])[:10], 30) is None

    # --- lead time, from the supplier's own orders -------------------------
    pos = [dict(p, PurchaseOrderDate="2026-08-01") for p in fx["PurchaseOrder"]
           if p["Material"] == "M-4471"]
    lt = lead_time_stats(pos, default_days=30, min_observations=2)
    assert not lt.assumed and lt.observations >= 2, lt
    thin = lead_time_stats(pos[:1], default_days=30, min_observations=2)
    assert thin.assumed and thin.sigma == 0.0 and "fewer than" in thin.note, thin
    print(f"  lead time        → {lt.mean:.0f} days, spread {lt.sigma:.1f} "
          f"over {lt.observations} orders · one order alone stays assumed ✓")

    # --- the cushion, and what the old flat floor got wrong ---------------
    pol = policy(*key, dm, lt, z=1.65, min_cover_days=14, order_cycle_days=30)
    flat = dm.mean * 14
    assert pol.safety_stock > 0
    print(f"  safety stock     → {pol.safety_stock:.0f} units "
          f"({pol.safety_days:.1f} days), reorder at {pol.reorder_point:.0f}")
    print(f"  the old policy   → a flat 14 days = {flat:.0f} units, "
          f"{'under' if flat < pol.reorder_point else 'over'} the calculated trigger "
          f"by {abs(flat - pol.reorder_point):.0f}")

    # A steady material must need a thinner cushion than a jumpy one, which is
    # the entire claim being made here.
    steady = Demand(mean=dm.mean, sigma=dm.sigma / 4, days=dm.days)
    thin_pol = policy(*key, steady, lt, 1.65, 14, 30)
    assert thin_pol.safety_stock < pol.safety_stock, (thin_pol.safety_stock,
                                                      pol.safety_stock)
    # And an unreliable supplier must widen it even when demand is identical.
    shaky = LeadTime(lt.mean, lt.sigma + 10, lt.observations)
    shaky_pol = policy(*key, dm, shaky, 1.65, 14, 30)
    assert shaky_pol.safety_stock > pol.safety_stock
    print(f"  steadier demand  → {thin_pol.safety_stock:.0f} units · "
          f"shakier supplier → {shaky_pol.safety_stock:.0f} units ✓")

    # A higher service level must cost stock, or the target means nothing.
    assert policy(*key, dm, lt, 2.33, 14, 30).safety_stock > pol.safety_stock

    # --- the order decision ----------------------------------------------
    on_hand = float(row["MatlWrhsStkQtyInMatlBaseUnit"])
    req = net_requirement(pol, on_hand, 0.0, 0.0, date.fromisoformat(fx["Profile"]["AsOfDate"]))
    assert req.status in ("order_now", "watch", "ok")
    print(f"  {key[0]} at {key[1]}  → {on_hand:.0f} on hand, {req.status}, "
          f"{req.reason}")
    if req.status == "order_now":
        assert req.order_qty > 0
        print(f"                     order {req.order_qty:.0f}, runs out {req.runs_out_on}")

    # Supply already in transit must count, or the planner orders twice.
    covered = net_requirement(pol, on_hand, pol.order_up_to * 2, 0.0)
    assert covered.status == "ok" and covered.order_qty == 0, covered

    # Stock promised to another handling is not available to this one.
    held = net_requirement(pol, on_hand, 0.0, on_hand)
    assert held.position == 0.0 and held.status == "order_now", held

    # No measured demand is not zero demand, and must not produce a figure.
    nil = net_requirement(policy(*key, Demand(0.0, 0.0, 120), lt, 1.65, 14, 30),
                          10.0, 0.0)
    assert nil.status == "no_demand" and nil.order_qty == 0.0, nil
    print("  no demand        → says so, rather than ordering against a zero ✓")

    # ---- the loop: recorded reality must change the next decision -------
    # This is the whole difference between an agent and a tidy script. Nothing
    # here edits a parameter; a delivery is observed to have run long and the
    # cushion behind it widens on its own.
    learned = lead_time_stats(pos, default_days=30, min_observations=2,
                              observed_days=[lt.mean + 21])
    assert learned.observations == lt.observations + 1, learned
    assert learned.mean > lt.mean and learned.sigma > lt.sigma, (learned, lt)
    assert "recorded outcomes" in learned.note, learned.note

    before = policy(*key, dm, lt, 1.65, 14, 30)
    after = policy(*key, dm, learned, 1.65, 14, 30)
    assert after.reorder_point > before.reorder_point, (after.reorder_point,
                                                        before.reorder_point)
    assert after.safety_stock > before.safety_stock
    print(f"  one late delivery → lead time {lt.mean:.0f}d becomes "
          f"{learned.mean:.0f}d, reorder point {before.reorder_point:.0f} becomes "
          f"{after.reorder_point:.0f} ✓")

    # An on-time delivery must not be punished as if it were late.
    ontime = lead_time_stats(pos, 30, 2, observed_days=[lt.mean])
    assert abs(ontime.mean - lt.mean) < 1.0, (ontime.mean, lt.mean)

    print("planning ok")


if __name__ == "__main__":
    demo()
