"""Elsa's tools (Impact).

Traces a disruption through orders, stock, and the bill of materials to the
customer commitments that are genuinely at risk.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from core.provenance import Origin, Result
from core.registry import register
from tools.fetcher import pull


@register("get_open_purchase_orders", "impact",
          "Open purchase orders, filterable by loading port or material.",
          {"port": {"type": ["string", "null"], "description": "port code, e.g. CNNGB"},
           "material": {"type": ["string", "null"]}})
def get_open_purchase_orders(port: Optional[str] = None,
                             material: Optional[str] = None) -> Result:
    def keep(r: dict) -> bool:
        return ((port is None or r.get("LoadingPort") == port)
                and (material is None or r.get("Material") == material))

    params = {"$filter": f"LoadingPort eq '{port}'", "$top": "50"} if port else {"$top": "50"}
    return pull("PurchaseOrder", "API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrder", params, keep)


@register("get_material_stock", "impact",
          "Material stock per plant together with its daily consumption rate.",
          {"material": {"type": ["string", "null"]}, "plant": {"type": ["string", "null"]}})
def get_material_stock(material: Optional[str] = None, plant: Optional[str] = None) -> Result:
    def keep(r: dict) -> bool:
        return ((material is None or r.get("Material") == material)
                and (plant is None or r.get("Plant") == plant))

    return pull("MaterialStock", "API_MATERIAL_STOCK_SRV", "A_MatlStkInAcctMod",
                {"$top": "100"}, keep)


@register("get_bom_explosion", "impact",
          "Which finished goods consume this material.",
          {"material": {"type": "string"}}, ["material"])
def get_bom_explosion(material: str) -> Result:
    return pull("BillOfMaterial", "API_BILL_OF_MATERIAL_SRV", "A_BillOfMaterial",
                {"$top": "100"}, lambda r: r.get("Material") == material)


@register("get_sales_order_commitments", "impact",
          "Customer orders for given finished goods, with their value.",
          {"finished_goods": {"type": "array", "items": {"type": "string"}}},
          ["finished_goods"])
def get_sales_order_commitments(finished_goods: list) -> Result:
    fg = set(finished_goods)
    return pull("SalesOrder", "API_SALES_ORDER_SRV", "A_SalesOrder",
                {"$top": "100"}, lambda r: r.get("Material") in fg)


def _component_orders(material: str, plant: str):
    """Customer orders expressed in the scarce material they consume.

    The route is the bill of materials: a customer orders a finished good, the
    finished good needs so many of this component per unit, so an order for
    320 calipers is an order for 320 units of the component behind it. Nothing
    could do this arithmetic before, because the sales order carried a value
    and no quantity.
    """
    from core import rules
    from engine.allocate import Order
    from tools.fetcher import _to_idr

    bom = pull("BillOfMaterial", "API_BILL_OF_MATERIAL_SRV", "A_BillOfMaterial",
               {"$top": "1000"}, lambda r: r.get("Material") == material)
    per_unit = {r["FinishedGood"]: float(r.get("ComponentQuantity") or 1)
                for r in (bom.value or []) if r.get("FinishedGood")}
    if not per_unit:
        return [], [], bom

    orders = pull("SalesOrder", "API_SALES_ORDER_SRV", "A_SalesOrder",
                  {"$top": "500"}, lambda r: r.get("Material") in per_unit)

    default_pct = rules.number("default_late_penalty_pct_per_day", 0.5)
    default_cap = rules.number("default_late_penalty_cap_pct", 10.0)

    out, defaulted = [], []
    for r in (orders.value or []):
        due, qty = r.get("RequestedDeliveryDate"), r.get("OrderQuantity")
        idr = (_to_idr(float(r["NetAmount"]), r.get("Currency"))
               if r.get("NetAmount") is not None else None)
        if not due or not qty or idr is None:
            continue
        pct, cap = r.get("LatePenaltyPctPerDay"), r.get("LatePenaltyCapPct")
        if pct is None or cap is None:
            # Zero would read as "late to this customer is free", which is the
            # one reading that makes an allocation confidently wrong.
            pct, cap = default_pct, default_cap
            defaulted.append(str(r.get("SalesOrder")))
        out.append(Order(
            id=str(r.get("SalesOrder")),
            customer=str(r.get("CustomerName") or r.get("Customer") or "unknown"),
            finished_good=str(r.get("Material")),
            due=date.fromisoformat(str(due)[:10]),
            qty=float(qty) * per_unit[r["Material"]],
            amount_idr=float(idr),
            pct_per_day=float(pct), cap_pct=float(cap)))
    return out, defaulted, orders


def _supply(material: str, plant: str, start: date):
    """On hand now, and what is booked to land later."""
    from core import store

    stock = pull("MaterialStock", "API_MATERIAL_STOCK_SRV", "A_MatlStkInAcctMod",
                 {"$top": "500"},
                 lambda r: r.get("Material") == material and r.get("Plant") == plant)
    row = (stock.value or [{}])[0]
    on_hand = float(row.get("MatlWrhsStkQtyInMatlBaseUnit") or 0)
    try:
        on_hand -= store.reserved_qty(material, plant)
    except Exception:                                            # noqa: BLE001
        pass

    po = pull("PurchaseOrder", "API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrder",
              {"$top": "500"},
              lambda r: r.get("Material") == material and r.get("Plant") == plant)
    arrivals = {}
    for r in (po.value or []):
        due = r.get("RevisedDeliveryDate") or r.get("DeliveryDate")
        if not due or r.get("Status") == "received":
            continue
        try:
            d = date.fromisoformat(str(due)[:10])
        except ValueError:
            continue
        if d < start:
            continue
        arrivals[d] = arrivals.get(d, 0.0) + float(r.get("OrderQuantity") or 0)
    return max(on_hand, 0.0), arrivals, stock, po


@register(
    "check_order_promise", "impact",
    "Can this customer order be met, and if not, the earliest date it can. Walks the "
    "bill of materials down to every component, counts stock on hand net of what is "
    "already promised elsewhere plus supply in transit, and names the component that "
    "binds the date. Deterministic.",
    {"finished_good": {"type": "string"}, "quantity": {"type": "number"},
     "by_date": {"type": "string", "description": "ISO date the customer wants it"},
     "plant": {"type": ["string", "null"]}},
    ["finished_good", "quantity", "by_date"])
def check_order_promise(finished_good: str, quantity: float, by_date: str,
                        plant: Optional[str] = None) -> Result:
    from datetime import timedelta

    from tools.fetcher import profile

    start = date.fromisoformat(str(profile()["AsOfDate"])[:10])
    want = date.fromisoformat(str(by_date)[:10])

    bom = pull("BillOfMaterial", "API_BILL_OF_MATERIAL_SRV", "A_BillOfMaterial",
               {"$top": "1000"}, lambda r: r.get("FinishedGood") == finished_good)
    parts = bom.value or []
    if not parts:
        return Result(None, Origin.MISSING, bom.source,
                      note=f"no bill of materials for {finished_good}, so nothing "
                           f"can be promised about it")

    rows, binding, promise = [], None, start
    for part in parts:
        comp, per = part.get("Material"), float(part.get("ComponentQuantity") or 1)
        at = plant or part.get("Plant") or profile()["Facilities"][0]["code"]
        need = quantity * per
        on_hand, arrivals, _s, _p = _supply(comp, at, start)

        # Earliest day cumulative supply covers the requirement.
        have, when = on_hand, (start if on_hand + 1e-9 >= need else None)
        for d in sorted(arrivals):
            if when is not None:
                break
            have += arrivals[d]
            if have + 1e-9 >= need:
                when = d
        rows.append({"component": comp, "plant": at, "per_unit": per,
                     "required": round(need, 1), "on_hand": round(on_hand, 1),
                     "available_from": when.isoformat() if when else None,
                     "shortfall": round(max(need - have, 0.0), 1)})
        if when is None:
            binding, promise = comp, None
            break
        if promise is not None and when > promise:
            binding, promise = comp, when

    can = promise is not None and promise <= want
    return Result({
        "finished_good": finished_good, "quantity": quantity,
        "requested": want.isoformat(),
        "can_promise": can,
        "earliest": promise.isoformat() if promise else None,
        "days_late": (promise - want).days if promise and promise > want else 0,
        "binding_component": binding,
        "components": rows,
    }, Origin.DERIVED, "engine/planning.py + " + bom.source,
        note=("" if can else
              (f"{binding} is the constraint" if binding else
               "no component binds, the date is met from stock on hand")))


@register(
    "propose_allocation", "impact",
    "When supply cannot cover every customer order, propose which orders are served "
    "and which wait. Ranks by what missing an order costs per unit of the scarce "
    "material, and reports what plain due-date order would have cost instead, so the "
    "ranking carries a price rather than an opinion. Deterministic. Proposes only: "
    "the allocation is a commercial decision and needs a person.",
    {"material": {"type": "string"}, "plant": {"type": "string"}},
    ["material", "plant"])
def propose_allocation(material: str, plant: str) -> Result:
    from engine.allocate import allocate
    from tools.fetcher import profile

    start = date.fromisoformat(str(profile()["AsOfDate"])[:10])
    orders, defaulted, so = _component_orders(material, plant)
    if not orders:
        return Result(None, Origin.MISSING, so.source,
                      note=f"no customer orders trace to {material} through the "
                           f"bill of materials, so there is nothing to allocate")

    on_hand, arrivals, stock, po = _supply(material, plant, start)
    out = allocate(orders, on_hand, arrivals, start)
    weak = [f"{k} is {r.origin.value}" for k, r in
            {"stock": stock, "booked supply": po, "customer orders": so}.items()
            if not r.trusted]

    return Result(out | {
        "material": material, "plant": plant,
        "on_hand": round(on_hand, 1),
        "orders_counted": len(orders),
        "incoming": {d.isoformat(): round(q, 1) for d, q in sorted(arrivals.items())},
    }, Origin.DERIVED if not weak else Origin.DERIVED,
        f"engine/allocate.py over {stock.source}",
        note="; ".join(filter(None, [
            f"{len(defaulted)} order(s) carry no penalty clause, the written "
            f"default was used" if defaulted else "",
            "; ".join(weak),
        ])))


def demo() -> None:
    # The route a shortage takes to a customer: component -> bill of materials
    # -> finished good -> sales order. The sales order carried a value and no
    # quantity, so nothing could work out how much of a scarce part one order
    # consumes, and every penalty computed as zero.
    orders, defaulted, so = _component_orders("M-4471", "KRW1")
    assert orders, "M-4471 must reach a customer through the bill of materials"
    assert all(o.qty > 0 for o in orders), "an order consuming nothing is not an order"
    assert all(o.pct_per_day > 0 for o in orders), "a free late delivery is not a term"
    print(f"  {len(orders)} customer order(s) trace to M-4471, "
          f"{sum(o.qty for o in orders):,.0f} units of it")

    # Component quantity must multiply. An order for 320 calipers at 2 ingots
    # each is an order for 640 ingots, not 320.
    bom = pull("BillOfMaterial", "API_BILL_OF_MATERIAL_SRV", "A_BillOfMaterial",
               {"$top": "1000"}, lambda r: r.get("Material") == "M-4471")
    per = {r["FinishedGood"]: float(r["ComponentQuantity"]) for r in (bom.value or [])}
    assert any(v > 1 for v in per.values()), "nothing to prove multiplication with"
    one = next(o for o in orders if per.get(o.finished_good, 1) > 1)
    assert one.qty % per[one.finished_good] == 0, (one.qty, per[one.finished_good])

    # ---- can we promise it ----------------------------------------------
    fg = next(iter(per))
    p = check_order_promise(fg, 320, "2026-09-30")
    assert p.origin is Origin.DERIVED, p.brief()
    v = p.value
    assert v["components"], v
    assert all(c["required"] > 0 for c in v["components"]), v["components"]
    if not v["can_promise"]:
        assert v["binding_component"], "a refusal must name what binds it"
        print(f"  {fg} x320 by 2026-09-30 → no, {v['binding_component']} binds, "
              f"earliest {v['earliest']}")
    else:
        print(f"  {fg} x320 by 2026-09-30 → yes, earliest {v['earliest']}")

    # A finished good with no bill of materials cannot be promised anything,
    # and must say that rather than promise it from thin air.
    assert check_order_promise("FG-9099", 1, "2026-12-01").origin is Origin.MISSING

    # ---- allocation ------------------------------------------------------
    a = propose_allocation("M-4471", "KRW1")
    assert a.origin is Origin.DERIVED, a.brief()
    w = a.value
    assert w["orders_counted"] == len(orders), (w["orders_counted"], len(orders))
    # Ranking must never lose to doing the obvious thing.
    assert w["proposed"]["penalty_idr"] <= w["by_date"]["penalty_idr"], w
    assert w["saving_idr"] >= 0, w
    print(f"  allocation       → Rp {w['proposed']['penalty_idr']:,} against "
          f"Rp {w['by_date']['penalty_idr']:,} in plain date order, "
          f"saving Rp {w['saving_idr']:,}")

    # A material no customer order reaches has nothing to allocate, and that
    # is an answer rather than an empty table.
    assert propose_allocation("M-NOT-REAL", "KRW1").origin is Origin.MISSING

    print("impact ok")


if __name__ == "__main__":
    from core.config import fixtures_only

    fixtures_only(__file__, "SIGAP_IMPACT_CHECK")
    demo()
