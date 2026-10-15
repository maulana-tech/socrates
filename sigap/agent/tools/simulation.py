"""Tara's tools (Costing).

A thin wrapper over engine/simulate.py. The model calls this tool; plain Python
still does the arithmetic. The model decides, the arithmetic computes.

Everything this file hands the engine now comes through the one read path, so
a live SAP tenant or an uploaded file reaches the calculator. It used to read
booked supply straight out of the fixture while claiming the answer was
derived from live data.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from core.provenance import Origin, Result
from core.registry import register
from engine.simulate import Arrival, Commitment, Ruling, simulate_scenario
from tools.compliance import check_local_constraints
from tools.fetcher import _to_idr, alternate_sources, profile, pull
from tools.impact import get_bom_explosion, get_material_stock


def _commitments(material: str) -> tuple[List[Commitment], List[str]]:
    """Customer orders exposed to this material running out.

    The route is the bill of materials: a component stops a finished good, and
    the finished good is what a customer ordered. The penalty terms have been
    sitting on these rows all along, unread.
    """
    bom = get_bom_explosion(material)
    goods = sorted({r["FinishedGood"] for r in (bom.value or [])
                    if r.get("FinishedGood")})
    if not goods:
        return [], []

    orders = pull("SalesOrder", "API_SALES_ORDER_SRV", "A_SalesOrder",
                  {"$top": "200"}, lambda r: r.get("Material") in set(goods))
    out: List[Commitment] = []
    for r in (orders.value or []):
        due, amount = r.get("RequestedDeliveryDate"), r.get("NetAmount")
        idr = _to_idr(float(amount), r.get("Currency")) if amount is not None else None
        # No date or no rupiah value means no penalty can be computed. The
        # order is left out rather than counted at zero, which would read as
        # "late to this customer is free".
        if not due or idr is None:
            continue
        out.append(Commitment(
            id=str(r.get("SalesOrder")),
            customer=str(r.get("CustomerName") or r.get("Customer") or "unknown"),
            due=date.fromisoformat(str(due)[:10]),
            amount_idr=float(idr),
            pct_per_day=float(r.get("LatePenaltyPctPerDay") or 0),
            cap_pct=float(r.get("LatePenaltyCapPct") or 0),
        ))
    return out, goods


@register(
    "simulate_scenario", "simulation",
    "Compute cost, stockout date, customer late-penalty exposure and TKDN impact for "
    "every supply option that cleared the rules, plus their combinations. Arrival "
    "dates already include the import permit, supplier qualification and port dwell. "
    "Returns chosen (cheapest plan with no shortfall), cheapest_total (lowest cost "
    "plus penalty, which may deliberately accept a short delivery), compliance_cost "
    "(what obeying the rules cost when a struck-out option was cheaper) and "
    "do_nothing_penalty. Deterministic. Refuses to emit figures when the inputs are "
    "not trustworthy.",
    {"material": {"type": "string"},
     "plant": {"type": "string"},
     "allowed_options": {"type": "array", "items": {"type": "string"},
                         "description": "option ids already cleared by Rules, e.g. ['A','B','C']"}},
    ["material", "plant"],
)
def simulate_scenario_tool(material: str, plant: str,
                           allowed_options: Optional[List[str]] = None) -> Result:
    p = profile()
    start = date.fromisoformat(p["AsOfDate"])

    stock = get_material_stock(material=material, plant=plant)
    row = (stock.value or [{}])[0]
    opening = row.get("MatlWrhsStkQtyInMatlBaseUnit")
    daily = row.get("DailyConsumption")
    if opening is None or daily is None:
        return Result(None, Origin.MISSING, "engine/simulate.py",
                      note=f"no stock found for {material} at {plant}")

    options = alternate_sources(material)

    # Compliance rulings come from Kira, never guessed here, and they carry
    # the effective arrival date so the plan is costed on when goods actually
    # land rather than on the date in master data.
    rulings = {}
    for o in (options.value or []):
        v = check_local_constraints(o["id"]).value or {}
        allowed = (o["id"] in allowed_options if allowed_options is not None
                   else bool(v.get("allowed")))
        rulings[o["id"]] = Ruling(o["id"], o["label"], allowed,
                                  v.get("reason", ""),
                                  arrival_effective=v.get("arrival_effective"))

    # Supply already booked and in transit, through the read path rather than
    # out of the fixture.
    booked = pull("PurchaseOrder", "API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrder",
                  {"$top": "200"},
                  lambda r: r.get("Material") == material and r.get("Plant") == plant)
    scheduled = [
        Arrival(str(r["PurchaseOrder"]),
                date.fromisoformat(str(r["RevisedDeliveryDate"])[:10]),
                float(r["OrderQuantity"]))
        for r in (booked.value or [])
        if r.get("RevisedDeliveryDate") and r.get("OrderQuantity")
    ]

    commitments, goods = _commitments(material)

    sim = simulate_scenario(stock, options, rulings, p, start,
                            float(daily), float(opening), scheduled, commitments)

    if sim.refused:
        return Result({"refused": True, "reason": sim.refusal_reason},
                      Origin.MISSING, "engine/simulate.py", note=sim.refusal_reason)

    # The weakest input decides the label. Booked supply and customer orders
    # feed the dates and the penalties, so a modelled read of either has to
    # show up on the answer rather than being hidden behind a derived stamp.
    inputs = {"stock": stock, "options": options, "booked supply": booked}
    weak = [f"{k} is {r.origin.value}" for k, r in inputs.items() if not r.trusted]

    return Result({
        "depleted_without_action": str(sim.depleted_without_action),
        "options": sim.options,
        "options_unplannable": sim.options_unplannable,
        "combinations": sim.combinations[:8],
        "chosen": sim.chosen,
        "cheapest_total": sim.cheapest_total,
        "do_nothing_penalty": sim.do_nothing_penalty,
        "compliance_cost": sim.compliance_cost,
        "finished_goods_at_risk": goods,
        "commitments_counted": len(commitments),
    }, Origin.DERIVED, "engine/simulate.py",
        note="; ".join(weak) if weak else "")
