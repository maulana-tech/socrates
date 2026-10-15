"""Data fetcher: try SAP first, fall back to fixtures when there's no key.

The point: falling back is NOT hidden. The origin becomes MODELLED, and that
shows up both in the UI and in the calculator's own trust check.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from clients import sap_s4
from core.provenance import Origin, Result

_FIXTURE = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "ningbo_scenario.json"
_cache: Optional[dict] = None


def fixture(entity: str) -> List[dict]:
    global _cache
    if _cache is None:
        _cache = json.loads(_FIXTURE.read_text())
    return _cache[entity]


def profile() -> dict:
    return fixture("Profile")  # type: ignore[return-value]


def pull(
    fixture_entity: str,
    sap_service: str,
    sap_entity: str,
    params: Optional[Dict] = None,
    keep: Optional[Callable[[dict], bool]] = None,
) -> Result:
    """One read path shared by every read tool."""
    if sap_s4.available():
        try:
            join = JOINS.get(fixture_entity)
            # A joined read ignores sap_entity: the caller named the header,
            # and the header alone is what used to come back without a
            # material on it.
            data = join() if join else sap_s4.rows(sap_s4.get(sap_service, sap_entity, params))
            if keep:
                data = [r for r in data if keep(r)]
            return Result(data, Origin.LIVE, sap_service)
        except Exception as e:                                   # noqa: BLE001
            return Result(None, Origin.MISSING, sap_service, note=f"{type(e).__name__}: {e}")

    # Real company data that was uploaded rather than pulled outranks a fixture:
    # it is genuine, just not live. Hence CACHED. A file the uploader declared
    # as generated stays MODELLED, because calling it cached would launder it.
    try:
        from core import store
        u = store.latest_upload(fixture_entity)
    except Exception:                                            # noqa: BLE001
        u = None
    if u:
        data = u["payload"]
        if keep:
            data = [r for r in data if keep(r)]
        generated = bool(u.get("synthetic"))
        return Result(
            data,
            Origin.MODELLED if generated else Origin.CACHED,
            f"upload:{u['filename']}",
            note=(f"uploaded {u['uploaded_at']}"
                  + (", declared as generated sample data" if generated else "")),
        )

    data = fixture(fixture_entity)
    if keep:
        data = [r for r in data if keep(r)]
    return Result(
        data, Origin.MODELLED, f"fixture:{fixture_entity}",
        note="SAP_API_KEY is not set. Using modelled data",
    )


# --------------------------------------------------------------- joined reads
#
# SAP keeps a purchase order across three entities and a bill of materials
# across two. The header carries the supplier, the item carries the material
# and the quantity, the schedule line carries the delivery date. Our engines
# want one row with all of it, which is what the fixtures always looked like,
# so the join happens here rather than in every tool that needs a purchase
# order. Reading only the header is what produced KeyError: 'Material'.
#
# $select is not an optimisation. The sandbox emits `"FixedQuantity":,` on the
# BOM item, which is not valid JSON, and naming the fields we want is what
# keeps that broken one out of the response.

_EPOCH = re.compile(r"^/Date\((-?\d+)([+-]\d+)?\)/$")


def sap_date(v) -> Optional[str]:
    """OData V2 dates arrive as /Date(1629936000000)/. Engines want ISO.

    Returns None rather than a guess when the value is not a date the format
    covers: a date nobody can read is better absent than silently wrong, and
    every caller here already treats a missing date as missing.
    """
    if not isinstance(v, str):
        return None
    m = _EPOCH.match(v)
    if not m:
        return v if len(v) >= 10 and v[4] == "-" else None
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date().isoformat()


def _sap_rows(service: str, entity: str, params: Dict) -> List[dict]:
    return sap_s4.rows(sap_s4.get(service, entity, params))


def _joined_purchase_orders(top: str = "200") -> List[dict]:
    """Header, item and schedule line as the single row the engines expect."""
    svc = "API_PURCHASEORDER_PROCESS_SRV"
    heads = {h["PurchaseOrder"]: h for h in _sap_rows(svc, "A_PurchaseOrder", {"$top": top})}
    items = _sap_rows(svc, "A_PurchaseOrderItem", {"$top": str(int(top) * 3)})
    sched = _sap_rows(svc, "A_PurchaseOrderScheduleLine", {"$top": str(int(top) * 3)})

    # Schedule lines key on PurchasingDocument, not PurchaseOrder. Earliest
    # line wins: that is the date the plant is planning against.
    when: Dict[tuple, str] = {}
    for sl in sched:
        k = (sl.get("PurchasingDocument"), sl.get("PurchasingDocumentItem"))
        d = sap_date(sl.get("ScheduleLineDeliveryDate"))
        if d and (k not in when or d < when[k]):
            when[k] = d

    out: List[dict] = []
    for it in items:
        mat = it.get("Material")
        if not mat:
            continue
        po, item = it.get("PurchaseOrder"), it.get("PurchaseOrderItem")
        head = heads.get(po, {})
        delivery = when.get((po, item))
        out.append({
            "PurchaseOrder": po,
            "Material": mat,
            "Plant": it.get("Plant"),
            "Supplier": head.get("Supplier") or it.get("Supplier"),
            "OrderQuantity": it.get("OrderQuantity"),
            "BaseUnit": it.get("PurchaseOrderQuantityUnit"),
            "DeliveryDate": delivery,
            # The engines read RevisedDeliveryDate as the date now expected.
            # Live SAP has one date per schedule line, so until a revision
            # exists the promised date and the expected date are the same.
            "RevisedDeliveryDate": delivery,
            "Status": head.get("PurchasingProcessingStatus"),
            # No SAP equivalent. The port a shipment loads at is not on the
            # purchase order, so lane concentration stays unanswerable from
            # live data and the tools that need it say so.
            "LoadingPort": None,
        })
    return out


# The component list is unreadable without naming the fields: see the comment
# above about the sandbox's invalid JSON.
_BOM_ITEM_FIELDS = ("BillOfMaterial,BillOfMaterialItemNumber,BillOfMaterialComponent,"
                    "BillOfMaterialItemQuantity,BillOfMaterialItemUnit")


def _joined_bom(top: str = "200") -> List[dict]:
    """Component to finished good, which is the direction the tools ask in."""
    svc = "API_BILL_OF_MATERIAL_SRV"
    heads = _sap_rows(svc, "A_BillOfMaterial", {"$top": top})
    made_by = {h["BillOfMaterial"]: h for h in heads}
    items = _sap_rows(svc, "A_BillOfMaterialItem",
                      {"$top": str(int(top) * 3), "$select": _BOM_ITEM_FIELDS})
    out: List[dict] = []
    for it in items:
        head = made_by.get(it.get("BillOfMaterial"))
        comp = it.get("BillOfMaterialComponent")
        if not head or not comp:
            continue
        out.append({
            "Material": comp,
            "FinishedGood": head.get("Material"),
            "Plant": head.get("Plant"),
            "Quantity": it.get("BillOfMaterialItemQuantity"),
            "BaseUnit": it.get("BillOfMaterialItemUnit"),
        })
    return out


def _joined_sales_orders(top: str = "200") -> List[dict]:
    """Committed customer value per material, which lives on the item."""
    svc = "API_SALES_ORDER_SRV"
    heads = {h["SalesOrder"]: h for h in _sap_rows(svc, "A_SalesOrder", {"$top": top})}
    items = _sap_rows(svc, "A_SalesOrderItem", {"$top": str(int(top) * 3)})
    out: List[dict] = []
    for it in items:
        mat = it.get("Material")
        if not mat:
            continue
        head = heads.get(it.get("SalesOrder"), {})
        out.append({
            "SalesOrder": it.get("SalesOrder"),
            "Material": mat,
            "Plant": it.get("Plant"),
            "NetAmount": float(it.get("NetAmount") or 0),
            "Currency": it.get("TransactionCurrency") or head.get("TransactionCurrency"),
            "RequestedDeliveryDate": sap_date(head.get("RequestedDeliveryDate")),
            "Customer": head.get("SoldToParty"),
        })
    return out


#: Reads that need more than one SAP entity to make one row.
JOINS = {
    "PurchaseOrder": _joined_purchase_orders,
    "BillOfMaterial": _joined_bom,
    "SalesOrder": _joined_sales_orders,
}


#: Every entity the audit reads, with the SAP service it would come from live.
ENTITIES = {
    "MaterialStock": ("API_MATERIAL_STOCK_SRV", "A_MatlStkInAcctMod"),
    "PurchaseOrder": ("API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrder"),
    "BillOfMaterial": ("API_BILL_OF_MATERIAL_SRV", "A_BillOfMaterial"),
    "SalesOrder": ("API_SALES_ORDER_SRV", "A_SalesOrder"),
    "AlternateSource": ("API_PURCHASING_INFO_RECORD_SRV", "A_PurchasingInfoRecord"),
    "Supplier": ("API_BUSINESS_PARTNER", "A_Supplier"),
    # The only entity carrying a price. ExtraCost on an alternate source is what
    # an option costs over the baseline; this is what a firm charges for a tonne.
    "Quotation": ("API_QTN_PROCESS_SRV", "A_SupplierQuotation"),
}


def current_dataset() -> tuple[dict, dict]:
    """Everything the system can currently see, by the same path the tools use.

    Returns the rows and, separately, where each entity came from. An audit that
    does not say which of its inputs were modelled is an audit of nothing.
    """
    data: Dict[str, list] = {}
    origins: Dict[str, dict] = {}
    for entity, (service, sap_entity) in ENTITIES.items():
        try:
            r = pull(entity, service, sap_entity, {"$top": "500"})
        except KeyError:
            # Not every entity exists in the fixture; Supplier is newer than it.
            continue
        data[entity] = r.value or []
        origins[entity] = {"origin": r.origin.value, "source": r.source, "note": r.note}
    return data, origins
