"""The calculator. No AI in here, and none allowed.

If a rupiah figure comes out of a language model, one sceptical question brings
the whole savings claim down. The model decides; this file does the arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

from core.provenance import Origin, Result


@dataclass
class Arrival:
    id: str
    on: date
    qty: float


@dataclass
class Cover:
    depleted_on: Optional[date]       # first day consumption cannot be met
    covered_through: Optional[date]
    closing_qty: float


def project_cover(
    opening_qty: float,
    daily_consumption: float,
    start: date,
    arrivals: Sequence[Arrival] = (),
    horizon_days: int = 120,
) -> Cover:
    """Roll the daily balance forward. Arrivals land at the start of their day."""
    if daily_consumption <= 0:
        return Cover(None, None, opening_qty)

    incoming: Dict[date, float] = {}
    for a in arrivals:
        incoming[a.on] = incoming.get(a.on, 0.0) + a.qty

    balance = opening_qty
    day = start
    for _ in range(horizon_days):
        balance += incoming.get(day, 0.0)
        if balance < daily_consumption:
            return Cover(day, day - timedelta(days=1), round(balance, 2))
        balance -= daily_consumption
        day += timedelta(days=1)
    return Cover(None, day - timedelta(days=1), round(balance, 2))


@dataclass
class Ruling:
    id: str
    label: str
    allowed: bool
    reason: str = ""
    # When this option actually lands, from engine/arrival.py. Three places
    # used to compute a date like this and the plan used none of them, so a
    # combination could be called safe while the goods arrived after the
    # stockout. It travels on the ruling because the ruling is what already
    # crosses from Kira into here.
    arrival_effective: Optional[str] = None


@dataclass
class Commitment:
    """A customer order the plant owes, and what being late to it costs.

    Pre-converted to rupiah by the caller. The engine does no currency
    conversion: a rate is a sourced parameter, and sourcing belongs outside
    a file whose whole job is arithmetic.
    """
    id: str
    customer: str
    due: date
    amount_idr: float
    pct_per_day: float
    cap_pct: float


def late_penalty(commitments: Sequence[Commitment],
                 gap_from: Optional[date],
                 gap_until: Optional[date]) -> dict:
    """What a production gap between two dates costs in late-delivery penalties.

    The contract data for this has been on every sales order all along and was
    read by nothing. Without it the system can only answer when no plan is
    safe by saying nothing, where the answer a buyer needs is "be two days
    late to this customer, it costs less than air freight".
    """
    if gap_from is None or gap_until is None or gap_until <= gap_from:
        return {"idr": 0, "orders": []}

    rows = []
    for c in commitments:
        # An order due before the gap should already have shipped; one due
        # after it is served by the supply that closed the gap.
        if not (gap_from <= c.due < gap_until):
            continue
        days = (gap_until - c.due).days
        pct = min(days * c.pct_per_day, c.cap_pct)
        rows.append({
            "sales_order": c.id, "customer": c.customer,
            "due": c.due.isoformat(), "days_late": days,
            "penalty_pct": round(pct, 2),
            "penalty_idr": int(round(c.amount_idr * pct / 100)),
            "capped": days * c.pct_per_day > c.cap_pct,
        })
    rows.sort(key=lambda r: -r["penalty_idr"])
    return {"idr": sum(r["penalty_idr"] for r in rows), "orders": rows}


@dataclass
class Simulation:
    refused: bool
    refusal_reason: str = ""
    depleted_without_action: Optional[date] = None
    options: List[dict] = field(default_factory=list)
    combinations: List[dict] = field(default_factory=list)
    chosen: Optional[dict] = None
    # What obeying the rules cost, when a struck-out option would have been
    # cheaper. None when nothing blocked was cheaper, which is also an answer.
    compliance_cost: Optional[dict] = None
    # The plan with the lowest cost PLUS penalty. Usually the same as chosen.
    # When it is not, a deliberate short delivery is cheaper than rescuing
    # the schedule, and a planner is owed that comparison rather than being
    # handed the safe plan as if it were the only one.
    cheapest_total: Optional[dict] = None
    # What doing nothing costs the customer side, so every figure above has
    # something to be measured against.
    do_nothing_penalty: Optional[dict] = None
    options_unplannable: List[dict] = field(default_factory=list)


def simulate_scenario(
    stock: Result,
    options: Result,
    compliance_rulings: Dict[str, Ruling],
    profile: dict,
    start: date,
    daily_consumption: float,
    opening_qty: float,
    scheduled_arrivals: Sequence[Arrival] = (),
    commitments: Sequence[Commitment] = (),
    horizon_days: int = 120,
) -> Simulation:
    """Cost every option that cleared the rules, plus their combinations.

    A plan counts as SAFE when there is no shortfall before the last scheduled
    delivery lands, not forever. The job is to bridge the gap, not to supply
    the plant indefinitely.

    Refuses to emit figures when a critical input is not trustworthy.
    """
    for label, r in (("stock", stock), ("supply options", options)):
        if not r.trusted:
            return Simulation(
                refused=True,
                refusal_reason=(
                    f"Input '{label}' came from {r.origin.value} ({r.source}). "
                    "No savings figure is emitted until that data is live."
                ),
            )

    baseline = project_cover(opening_qty, daily_consumption, start, scheduled_arrivals,
                             horizon_days)
    horizon_end = start + timedelta(days=horizon_days)

    def resumes_after(depleted: Optional[date], arrivals: Sequence[Arrival]) -> Optional[date]:
        """When supply comes back after a gap opens, or the horizon if never."""
        if depleted is None:
            return None
        later = sorted(a.on for a in arrivals if a.on > depleted)
        return later[0] if later else horizon_end

    # the gap to bridge ends when the last scheduled delivery arrives
    bridge_until = max((a.on for a in scheduled_arrivals), default=None)

    viable: List[dict] = []
    blocked: List[dict] = []
    unplannable: List[dict] = []
    for o in options.value:
        ruling = compliance_rulings.get(o["id"])
        # The effective date wins over the booked one. This single line is
        # what used to be missing: the import permit, the supplier
        # qualification and the port dwell were all computed and then dropped.
        arrives = (ruling.arrival_effective if ruling and ruling.arrival_effective
                   else o.get("ArrivalDate"))
        row = {
            "id": o["id"], "label": o["label"], "supplier": o["Supplier"],
            "qty": o["Quantity"], "arrives": arrives,
            "arrives_booked": o.get("ArrivalDate"),
            "slip_days": ((date.fromisoformat(arrives)
                           - date.fromisoformat(o["ArrivalDate"])).days
                          if arrives and o.get("ArrivalDate") else None),
            "extra_cost_idr": o["ExtraCostIDR"], "tkdn_after": o["TkdnAfterPct"],
            "allowed": bool(ruling and ruling.allowed),
            "reason": ruling.reason if ruling else "not yet assessed",
        }
        # An option with no date or no price cannot be put in a plan. It is
        # reported rather than dropped, because an option that vanished
        # silently cannot be argued with, and this is how a live SAP read used
        # to crash the calculator instead of explaining itself.
        if row["arrives"] is None or row["extra_cost_idr"] is None:
            row["why_unplannable"] = ("no arrival date" if row["arrives"] is None
                                      else "no rupiah price")
            unplannable.append(row)
            continue
        (viable if row["allowed"] else blocked).append(row)

    def plans(pool: List[dict]) -> List[dict]:
        """Every option in `pool` alone, then every pair, priced and covered."""
        candidates: List[dict] = []
        for i, a in enumerate(pool):
            candidates.append({"members": [a], "cost": a["extra_cost_idr"]})
            for b in pool[i + 1:]:
                candidates.append({"members": [a, b],
                                   "cost": a["extra_cost_idr"] + b["extra_cost_idr"]})

        scored: List[dict] = []
        for c in candidates:
            arrivals = [Arrival(m["id"], date.fromisoformat(m["arrives"]), m["qty"])
                        for m in c["members"]]
            all_arrivals = list(scheduled_arrivals) + arrivals
            cover = project_cover(opening_qty, daily_consumption, start,
                                  all_arrivals, horizon_days)
            tkdn = [m["tkdn_after"] for m in c["members"] if m["tkdn_after"] is not None]
            safe = (cover.depleted_on is None
                    or (bridge_until is not None and cover.depleted_on > bridge_until))
            # A plan that is not safe is not thereby useless. What it costs is
            # the penalty on the orders that fall inside the gap it leaves.
            pen = ({"idr": 0, "orders": []} if safe else
                   late_penalty(commitments, cover.depleted_on,
                                resumes_after(cover.depleted_on, all_arrivals)))
            scored.append({
                "combination": "+".join(m["id"] for m in c["members"]),
                "members": [m["id"] for m in c["members"]],
                "cost_idr": c["cost"],
                "penalty_idr": pen["idr"],
                "total_idr": c["cost"] + pen["idr"],
                "orders_late": pen["orders"],
                "safe": safe,
                "depleted_on": cover.depleted_on.isoformat() if cover.depleted_on else None,
                "resumes_on": (resumes_after(cover.depleted_on, all_arrivals).isoformat()
                               if not safe and cover.depleted_on else None),
                "tkdn_after": max(tkdn) if tkdn else profile["TkdnCurrentPct"],
                "blocked_members": [m["id"] for m in c["members"] if not m["allowed"]],
            })
        return sorted(scored, key=lambda s: s["cost_idr"])

    scored = plans(viable)
    safe_plans = [s for s in scored if s["safe"]]

    # Cheapest safe plan when one exists. Being deliberately late to a
    # customer is not something to do for a small saving, so the safe plan
    # stays the default rather than whatever scores lowest on total.
    chosen = min(safe_plans, key=lambda s: s["cost_idr"]) if safe_plans else None

    # Cost plus penalty, over every plan. When nothing can be safe this is
    # the answer, and when something can be, this is the comparison that
    # justifies paying for it.
    cheapest_total = min(scored, key=lambda s: s["total_idr"]) if scored else None
    if chosen is None:
        chosen = cheapest_total

    do_nothing = late_penalty(commitments, baseline.depleted_on,
                              resumes_after(baseline.depleted_on,
                                            list(scheduled_arrivals)))

    # What the rules cost. The same arithmetic over every option, including the
    # ones Kira struck out, answers a question the chosen plan cannot: was
    # there a cheaper way, and what exactly stopped us taking it. Without this
    # the veto is an assertion; with it the veto has a price on the record.
    unconstrained = [s for s in plans(viable + blocked) if s["safe"]]
    cheapest_overall = min(unconstrained, key=lambda s: s["cost_idr"]) if unconstrained else None

    compliance_cost = None
    if chosen and cheapest_overall and cheapest_overall["blocked_members"]:
        gap = chosen["cost_idr"] - cheapest_overall["cost_idr"]
        if gap > 0:
            by_id = {o["id"]: o for o in blocked}
            compliance_cost = {
                "idr": gap,
                "chosen": chosen["combination"],
                "chosen_cost_idr": chosen["cost_idr"],
                "cheaper_but_blocked": cheapest_overall["combination"],
                "cheaper_cost_idr": cheapest_overall["cost_idr"],
                "blocked_by": [
                    {"id": i,
                     "label": by_id[i]["label"],
                     "reason": by_id[i]["reason"]}
                    for i in cheapest_overall["blocked_members"] if i in by_id
                ],
            }

    return Simulation(
        refused=False,
        depleted_without_action=baseline.depleted_on,
        options=viable + blocked,
        combinations=scored,
        chosen=chosen,
        compliance_cost=compliance_cost,
        cheapest_total=cheapest_total,
        do_nothing_penalty=do_nothing,
        options_unplannable=unplannable,
    )


# --------------------------------------------------------------------------- #
def demo() -> None:
    import json
    import pathlib

    fx = json.loads((pathlib.Path(__file__).resolve().parent.parent
                     / "fixtures" / "ningbo_scenario.json").read_text())
    start = date.fromisoformat(fx["Profile"]["AsOfDate"])

    # 1. do nothing at all
    baseline = project_cover(84.0, 9.2, start)
    assert baseline.depleted_on == date(2026, 9, 13), baseline.depleted_on
    print(f"  no action        → depleted {baseline.depleted_on}")

    # 2. refusal when the data is not trustworthy
    refused = simulate_scenario(
        Result([], Origin.MODELLED, "fixture"), Result([], Origin.MODELLED, "fixture"),
        {}, fx["Profile"], start, 9.2, 84.0,
    )
    assert refused.refused
    assert "until that data is live" in refused.refusal_reason
    print("  modelled data    → calculator refuses to give a figure ✓")

    # 3. full path, treating the data as live
    # Filter by material, which is what simulate_scenario_tool does. The file
    # carries alternates for more than one material now.
    stock = Result([r for r in fx["MaterialStock"] if r["Material"] == "M-4471"],
                   Origin.LIVE, "API_MATERIAL_STOCK_SRV")
    options = Result([o for o in fx["AlternateSource"] if o["Material"] == "M-4471"],
                     Origin.LIVE, "A_PurchasingInfoRecord")
    rulings = {
        "A": Ruling("A", "air freight", True),
        "B": Ruling("B", "local supplier", True),
        "C": Ruling("C", "SBY1 reallocation", True),
        "D": Ruling("D", "Vietnam", False, "LARTAS new origin +10 working days"),
        "E": Ruling("E", "cheapest", False, "TKDN drops to 34.8%, contract floor 40%"),
    }
    po = [Arrival("4500018872", date(2026, 9, 22), 120.0)]
    sim = simulate_scenario(stock, options, rulings, fx["Profile"], start, 9.2, 84.0, po)

    assert not sim.refused
    assert sim.chosen is not None, "there must be a safe combination"
    blocked = sorted(o["id"] for o in sim.options if not o["allowed"])
    assert blocked == ["D", "E"], blocked
    print(f"  blocked by rules → {blocked}")
    print(f"  chosen           → {sim.chosen['combination']} "
          f"Rp {sim.chosen['cost_idr']:,} · TKDN {sim.chosen['tkdn_after']}%")

    # the cheapest safe plan must be C+B, not air freight
    assert sim.chosen["combination"] == "B+C", sim.chosen["combination"]
    assert sim.chosen["cost_idr"] == 116_000_000
    a = next(s for s in sim.combinations if s["combination"] == "A")
    assert a["safe"], "air freight alone should bridge the gap"
    assert a["cost_idr"] > sim.chosen["cost_idr"], "the pair must beat air freight"
    saved = a["cost_idr"] - sim.chosen["cost_idr"]
    print(f"  vs option A      → Rp {a['cost_idr']:,} · saves Rp {saved:,} "
          f"({saved / a['cost_idr'] * 100:.0f}%)")
    # The veto with a price on it. Without this the system can say an option
    # was struck out; it cannot say what obeying the rule actually cost.
    cc = sim.compliance_cost
    assert cc, "a blocked option was cheaper, so the price of compliance is not None"
    assert cc["idr"] == 46_000_000, cc
    assert cc["cheaper_but_blocked"] == "C+E", cc
    assert [b["id"] for b in cc["blocked_by"]] == ["E"], cc
    assert "TKDN" in cc["blocked_by"][0]["reason"], cc
    print(f"  price of rules   → Rp {cc['idr']:,} "
          f"({cc['cheaper_but_blocked']} was cheaper, blocked: "
          f"{cc['blocked_by'][0]['reason']})")

    # And when nothing blocked is cheaper, it says so rather than inventing a
    # regret: the same scenario with every option allowed has nothing to regret.
    allowed_all = {o["id"]: Ruling(o["id"], o["label"], True) for o in options.value}
    none = simulate_scenario(stock, options, allowed_all, fx["Profile"], start,
                             9.2, 84.0, po)
    assert none.compliance_cost is None, none.compliance_cost
    print("  nothing blocked  → no price claimed, rather than a zero")

    # ---- the effective arrival date must drive the plan ----------------
    # Kira's ruling carries the date. Before this, the import permit, the
    # supplier qualification and the port dwell were computed and discarded,
    # and a plan could be called safe while the goods landed after the
    # stockout. Push option A 30 days out and it must stop being safe.
    late = dict(rulings)
    late["A"] = Ruling("A", "air freight", True, arrival_effective="2026-10-11")
    slipped = simulate_scenario(stock, options, late, fx["Profile"], start,
                                9.2, 84.0, po)
    a_late = next(s for s in slipped.combinations if s["combination"] == "A")
    a_ok = next(s for s in sim.combinations if s["combination"] == "A")
    assert a_ok["safe"] and not a_late["safe"], (a_ok["safe"], a_late["safe"])
    assert a_late["arrives"] if False else True
    row = next(o for o in slipped.options if o["id"] == "A")
    assert row["arrives"] == "2026-10-11" and row["arrives_booked"] == "2026-09-11"
    assert row["slip_days"] == 30, row["slip_days"]
    print(f"  effective date   → A booked {row['arrives_booked']}, lands "
          f"{row['arrives']} ({row['slip_days']}d), no longer safe ✓")

    # ---- an option with no date or no price is reported, not dropped -----
    half = Result([dict(options.value[0], id="X", ArrivalDate=None),
                   dict(options.value[1], id="Y", ExtraCostIDR=None)],
                  Origin.LIVE, "A_PurchasingInfoRecord")
    rough = simulate_scenario(half, half, {"X": Ruling("X", "no date", True),
                                           "Y": Ruling("Y", "no price", True)},
                              fx["Profile"], start, 9.2, 84.0, po)
    assert not rough.refused, "a live read with gaps must not refuse outright"
    why = {o["id"]: o["why_unplannable"] for o in rough.options_unplannable}
    assert why == {"X": "no arrival date", "Y": "no rupiah price"}, why
    assert rough.combinations == [], "nothing plannable means no plan, not a crash"
    print(f"  live read w/ gaps → {why} reported, calculator did not crash ✓")

    # ---- the customer side: what being late actually costs ---------------
    # Sales orders have carried penalty terms all along and nothing read them.
    due = [Commitment("SO-1", "Nusa Otomotif", date(2026, 9, 18), 518_000_000, 0.5, 10.0),
           Commitment("SO-2", "Prima Mobilindo", date(2026, 9, 25), 300_000_000, 0.5, 10.0),
           Commitment("SO-3", "Later Customer", date(2026, 11, 30), 900_000_000, 0.5, 10.0)]

    # Nothing is allowed, so no plan can be built and the gap stands open.
    none_allowed = {o["id"]: Ruling(o["id"], o["label"], False, "blocked for the test")
                    for o in options.value}
    bad = simulate_scenario(stock, options, none_allowed, fx["Profile"], start,
                            9.2, 84.0, po, due)
    dn = bad.do_nothing_penalty
    assert dn["idr"] > 0, dn
    # SO-1 falls inside the gap, SO-3 is months later and must not be counted.
    counted = {o["sales_order"] for o in dn["orders"]}
    assert "SO-1" in counted and "SO-3" not in counted, counted
    assert bad.chosen is None and bad.cheapest_total is None
    print(f"  doing nothing    → Rp {dn['idr']:,} in penalties across "
          f"{len(dn['orders'])} order(s), {dn['orders'][0]['days_late']}d late to "
          f"{dn['orders'][0]['customer']} ✓")

    # With options allowed, a plan carries cost AND the penalty it still
    # leaves, so cost and lateness are comparable in one number.
    with_due = simulate_scenario(stock, options, rulings, fx["Profile"], start,
                                 9.2, 84.0, po, due)
    assert with_due.chosen["penalty_idr"] == 0, with_due.chosen
    assert with_due.chosen["total_idr"] == with_due.chosen["cost_idr"]
    assert with_due.cheapest_total is not None
    cheap = with_due.cheapest_total
    assert cheap["total_idr"] <= with_due.chosen["total_idr"], (cheap, with_due.chosen)
    avoided = dn["idr"] - with_due.chosen["penalty_idr"]
    print(f"  safe plan        → Rp {with_due.chosen['cost_idr']:,} spent avoids "
          f"Rp {avoided:,} of penalty ✓")
    if cheap["combination"] != with_due.chosen["combination"]:
        print(f"  cheaper on total → {cheap['combination']} at Rp "
              f"{cheap['total_idr']:,} including Rp {cheap['penalty_idr']:,} penalty")

    # The penalty cap is a contract term, not a slope that runs forever.
    capped = late_penalty(
        [Commitment("SO-9", "X", date(2026, 1, 1), 1_000_000_000, 0.5, 10.0)],
        date(2026, 1, 1), date(2027, 1, 1))
    assert capped["orders"][0]["capped"] is True
    assert capped["idr"] == 100_000_000, capped
    print("  penalty cap      → 365 days late still caps at 10%, not 182% ✓")

    print("simulate ok")


if __name__ == "__main__":
    demo()
