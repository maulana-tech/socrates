"""Iris's tools (Stock Validity).

Stock that is recorded as present is not automatically stock you may use.
This file answers the 'may use' half: quality holds and safety stock.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from datetime import date

from core import rules
from core.provenance import Origin, Result
from core.registry import register
from tools.fetcher import profile, pull


@register("get_quality_holds", "inventory",
          "Stock that is on the books but blocked pending a quality inspection.",
          {"material": {"type": "string"}, "plant": {"type": "string"}},
          ["material", "plant"])
def get_quality_holds(material: str, plant: str) -> Result:
    return Result([], Origin.MODELLED, "API_INSPECTIONLOT_SRV",
                  note="the fixture carries no quality holds for this scenario")


def policies(material: Optional[str] = None, plant: Optional[str] = None):
    """Stock policies for every position, or a filtered subset.

    Batched on purpose. The single-material version reads stock, purchase
    orders and withdrawal history once each; doing that per material across a
    few hundred positions is a few hundred round trips for one daily review.
    """
    from engine.planning import demand_stats, lead_time_stats, policy
    from tools.demand import history_rows

    stock = pull("MaterialStock", "API_MATERIAL_STOCK_SRV", "A_MatlStkInAcctMod",
                 {"$top": "1000"},
                 lambda r: ((material is None or r.get("Material") == material)
                            and (plant is None or r.get("Plant") == plant)))
    orders = pull("PurchaseOrder", "API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrder",
                  {"$top": "1000"})
    rows, hist_source = history_rows()

    series: Dict[Tuple[str, str], List[Tuple[date, float]]] = {}
    for h in rows:
        try:
            key = (h["Material"], h["Plant"])
            series.setdefault(key, []).append(
                (date.fromisoformat(str(h["Date"])[:10]), float(h["Quantity"])))
        except (KeyError, TypeError, ValueError):
            continue

    by_material: Dict[str, List[dict]] = {}
    suppliers_of: Dict[str, set] = {}
    for o in (orders.value or []):
        if o.get("Material"):
            by_material.setdefault(o["Material"], []).append(o)
            if o.get("Supplier"):
                suppliers_of.setdefault(o["Material"], set()).add(str(o["Supplier"]))

    # Deliveries this system watched land, keyed by who delivered them. This
    # is what makes the policy move on its own when reality disagrees with
    # the paperwork.
    observed: Dict[str, List[float]] = {}
    try:
        from core import store
        for obs in store.delivery_observations():
            if obs["supplier"]:
                observed.setdefault(str(obs["supplier"]), []).append(float(obs["days"]))
            if obs["material"]:
                observed.setdefault(f"material:{obs['material']}", []).append(
                    float(obs["days"]))
    except Exception:                                            # noqa: BLE001
        observed = {}

    min_days = rules.whole("min_history_days", 30)
    min_obs = rules.whole("min_lead_time_observations", 2)
    default_lt = rules.number("default_lead_time_days", 30.0)
    z = rules.number("service_level_z", 1.65)
    floor_days = rules.number("min_cover_days", 14.0)
    cycle = rules.number("order_cycle_days", 30.0)

    out, skipped = [], []
    for r in (stock.value or []):
        m, pl = r.get("Material"), r.get("Plant")
        if not m or not pl:
            continue
        planned = (float(r["DailyConsumption"])
                   if r.get("DailyConsumption") is not None else None)
        dm = demand_stats(sorted(series.get((m, pl), [])), min_days, planned)
        if dm is None:
            skipped.append({"material": m, "plant": pl,
                            "why": f"{len(series.get((m, pl), []))} days of history, "
                                   f"fewer than {min_days}"})
            continue
        seen: List[float] = list(observed.get(f"material:{m}", []))
        for sup in suppliers_of.get(m, ()):
            seen += observed.get(sup, [])
        lt = lead_time_stats(by_material.get(m, []), default_lt, min_obs, seen)
        out.append((policy(m, pl, dm, lt, z, floor_days, cycle), r))

    return out, skipped, stock, orders, hist_source


def policy_for(material: str, plant: str) -> Tuple[Optional[object], Result]:
    """One position's policy, and where every input came from.

    Public because Prita's replenishment review needs the same policy Iris
    publishes. Two implementations of a reorder point is how the two stop
    agreeing.
    """
    found, skipped, stock, orders, hist = policies(material, plant)
    if not found:
        why = (skipped[0]["why"] if skipped
               else f"no stock record for {material} at {plant}")
        return None, Result(
            None, Origin.MISSING, hist if skipped else stock.source,
            note=(f"{why}. Upload movement history for this material, or set the "
                  f"floor by hand" if skipped else why))

    pol, _row = found[0]
    origin = (Origin.DERIVED if stock.origin is not Origin.MISSING
              else Origin.MISSING)
    return pol, Result(pol.as_dict(), origin,
                       f"engine/planning.py over {hist} + {stock.source}",
                       note=("lead time assumed, no delivered order to measure"
                             if pol.lead_time.assumed else ""))


@register("get_safety_stock_policy", "inventory",
          "The safety stock and reorder point for one material at one plant, computed "
          "from its measured daily use and its supplier's measured lead time against "
          "the service level in references/operating-targets.md. Returns the numbers "
          "and the reasons that produced them. Refuses when the withdrawal history is "
          "too short to size a cushion from.",
          {"material": {"type": "string"}, "plant": {"type": "string"}},
          ["material", "plant"])
def get_safety_stock_policy(material: str, plant: str) -> Result:
    # This used to return MISSING for everything, and the only policy in the
    # system was a fourteen day floor sitting in a default argument.
    return policy_for(material, plant)[1]


@register("assess_transfer", "inventory",
          "Judge one proposed inter-plant transfer from both ends. The receiving plant "
          "is easy to model and the donor is the one that gets forgotten. Returns "
          "whether the donor keeps its own safety floor, and when it would empty if it "
          "does not. A transfer that breaks the sender is not a solution.",
          {"material": {"type": "string"}, "from_plant": {"type": "string"},
           "to_plant": {"type": "string"}, "qty": {"type": "number"},
           "floor_days": {"type": "integer", "description": "safety floor, default 14"}},
          ["material", "from_plant", "to_plant", "qty"])
def net_of_reservations(rows: list, material: str, plant: str) -> tuple[list, float]:
    """Stock rows with another handling's promises taken out, and how much.

    Two handlings read the same on-hand figure, so each is right alone and
    they are wrong together. Anything that judges whether a plant can spare
    stock has to come through here, or it will read a number that is already
    spoken for. Returns the adjusted rows and the quantity held elsewhere.
    """
    from core import registry, store

    held = store.reserved_qty(material, plant, excluding_run=registry.current_run())
    if not held:
        return rows, 0.0
    out = [dict(r) for r in rows]
    for r in out:
        if r.get("Material") == material and r.get("Plant") == plant:
            on_hand = r.get("MatlWrhsStkQtyInMatlBaseUnit")
            if on_hand is not None:
                r["MatlWrhsStkQtyInMatlBaseUnit"] = max(0.0, float(on_hand) - held)
    return out, held


def assess_transfer(material: str, from_plant: str, to_plant: str, qty: float,
                    floor_days: int = 14) -> Result:
    from engine.matching import assess

    stock = pull("MaterialStock", "API_MATERIAL_STOCK_SRV", "A_MatlStkInAcctMod",
                 {"$top": "500"})
    if not stock.value:
        return Result(None, Origin.MISSING, stock.source, note="no stock records to judge")
    start = date.fromisoformat(profile()["AsOfDate"])

    rows, held = net_of_reservations(stock.value, material, from_plant)
    t = assess(rows, material, from_plant, to_plant, qty, start, floor_days)
    out = t.as_dict()
    out["reserved_elsewhere"] = held
    note = t.reason
    if held:
        note = f"{note} ({held:g} already held by another handling)"
    return Result(out, stock.origin, stock.source, note=note)


def demo() -> None:
    # The policy has to be computed, not copied. Before this, every material
    # in the system shared one fourteen day floor sitting in a default
    # argument, and get_safety_stock_policy returned MISSING for everything.
    found, skipped, stock, orders, hist = policies()
    assert found, "no position could be planned at all"
    print(f"  {len(found)} position(s) planned, {len(skipped)} without enough history")

    pol, row = next((p, r) for p, r in found if p.material == "M-4471"
                    and p.plant == "KRW1")
    assert pol.demand.days >= 30, pol.demand
    assert pol.demand.sigma > 0, "a flat series makes the whole exercise pointless"
    assert pol.safety_stock > 0 and pol.reorder_point > pol.safety_stock
    print(f"  M-4471 at KRW1: demand {pol.demand.mean:.2f}/day ± {pol.demand.sigma:.2f}, "
          f"lead {pol.lead_time.mean:.0f}d ± {pol.lead_time.sigma:.1f}, "
          f"safety {pol.safety_stock:.0f} ({pol.safety_days:.1f}d), "
          f"reorder at {pol.reorder_point:.0f}")

    # Every position must differ from every other, or a formula is being
    # reported where a constant is being used.
    points = {(p.material, p.plant): round(p.reorder_point, 1) for p, _ in found}
    assert len(set(points.values())) > len(points) // 2, \
        "too many positions share a reorder point to be a calculation"

    # The published tool must agree with the batch, and carry its reasons.
    one = get_safety_stock_policy("M-4471", "KRW1")
    assert one.origin is Origin.DERIVED and one.trusted, one.brief()
    assert one.value["reorder_point"] == round(pol.reorder_point, 1), one.value
    assert len(one.value["reasons"]) >= 3, one.value["reasons"]

    # A material with no history must refuse rather than take a default.
    nope = get_safety_stock_policy("M-NOT-REAL", "KRW1")
    assert nope.origin is Origin.MISSING and nope.value is None, nope.brief()
    assert "no stock record" in nope.note or "history" in nope.note, nope.note
    print(f"  unknown material → {nope.origin.value}, '{nope.note[:48]}...' ✓")

    print("inventory ok")


if __name__ == "__main__":
    from core.config import fixtures_only

    fixtures_only(__file__, "SIGAP_INVENTORY_CHECK")
    demo()
