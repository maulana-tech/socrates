"""Milo's tools (Logistics).

Arrival dates that survive contact with reality: port dwell and customs
clearance are computed, not guessed by the model.
"""
from __future__ import annotations

from typing import Optional

from core.provenance import Origin, Result
from core.registry import register
from tools.fetcher import alternate_source, pull


@register("estimate_eta", "logistics",
          "The date a supply option actually lands, with every correction named: "
          "import permit, supplier qualification, port dwell. Deterministic, and the "
          "same arithmetic the rules check and the costing engine use, so the three "
          "cannot drift apart.",
          {"option_id": {"type": "string"},
           "dwell_days": {"type": ["integer", "null"],
                          "description": "override port dwell. Default is the written "
                                         "figure in references/priok-dwell-time.md"}},
          ["option_id"])
def estimate_eta(option_id: str, dwell_days: Optional[int] = None) -> Result:
    # This used to carry its own dwell default of 4 while the written rule
    # said 5, and its own answer which the plan then ignored. Both are now
    # one thing: engine/arrival.py, reached through the same helper Kira uses.
    from tools.compliance import arrival_for

    o = alternate_source(option_id)
    if o is None:
        return Result(None, Origin.MISSING, "engine/arrival.py",
                      note=f"unknown option '{option_id}'")
    est = arrival_for(o, dwell_days)
    if est is None:
        return Result(None, Origin.MISSING, "engine/arrival.py",
                      note=f"option '{option_id}' carries no booked arrival date")
    return Result(est.as_dict() | {"option_id": option_id},
                  Origin.DERIVED, "engine/arrival.py + references/")


@register("get_shipment_status", "logistics",
          "Position and status of a shipment in transit.",
          {"purchase_order": {"type": "string"}}, ["purchase_order"])
def get_shipment_status(purchase_order: str) -> Result:
    got = pull("PurchaseOrder", "API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrder",
               {"$top": "200"},
               lambda x: str(x.get("PurchaseOrder")) == str(purchase_order))
    r = (got.value or [None])[0]
    if r is None:
        return Result(None, Origin.MISSING, got.source,
                      note=f"no purchase order {purchase_order} on this tenant")
    return Result({"purchase_order": purchase_order, "status": r.get("Status"),
                   "arrival_original": r.get("DeliveryDate"),
                   "arrival_revised": r.get("RevisedDeliveryDate")},
                  got.origin, got.source, note=got.note)
