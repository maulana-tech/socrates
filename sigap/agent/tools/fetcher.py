"""Data fetcher: try SAP first, fall back to fixtures when there's no key.

The point: falling back is NOT hidden. The origin becomes MODELLED, and that
shows up both in the UI and in the calculator's own trust check.
"""
from __future__ import annotations

import json
import pathlib
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

from clients import sap_s4
from core import rules
from core.provenance import Origin, Result

_FIXTURE = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "ningbo_scenario.json"
_cache: Optional[dict] = None


def fixture(entity: str) -> List[dict]:
    global _cache
    if _cache is None:
        _cache = json.loads(_FIXTURE.read_text())
    return _cache[entity]


#: Company-level profile columns an engine actually reads.
PROFILE_FIELDS = ("Company", "AsOfDate", "TkdnCurrentPct", "TkdnContractFloorPct")


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _profile_from_upload(rows: list) -> Tuple[Optional[dict], List[str]]:
    """One flat CSV into the nested profile, or None and what it was missing.

    An ERP extract is flat, so a profile arrives denormalised: the company
    columns repeat on every row and each row carries one facility. Rebuilding
    it here beats asking an operator to hand-write nested JSON.
    """
    head = rows[0] if rows and isinstance(rows[0], dict) else {}
    missing = [k for k in PROFILE_FIELDS if head.get(k) in (None, "")]
    facilities = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("code"):
            continue
        lat, lon = _num(r.get("lat")), _num(r.get("lon"))
        if lat is None or lon is None:
            continue
        facilities.append({"code": str(r["code"]), "kind": str(r.get("kind") or "plant"),
                           "name": str(r.get("name") or r["code"]), "lat": lat, "lon": lon})
    if not facilities:
        missing.append("a facility row carrying code, lat and lon")
    if missing:
        return None, missing
    return {k: head[k] for k in PROFILE_FIELDS} | {"Facilities": facilities}, []


def profile_result() -> Result:
    """Whose installation this is, and how we know.

    Every other entity already lets a company's own upload outrank the built-in
    figures. The profile did not, so an operator who loaded their own master
    data was still judged against the reference installation's TKDN position
    and measured against its plant coordinates. That is the one place where a
    worked example quietly became an assumption about the customer.
    """
    own = _uploaded("Profile", None)
    if own is not None and own.value:
        built, missing = _profile_from_upload(own.value)
        if built is not None:
            return Result(built, own.origin, own.source, note=own.note)
        # Half a profile is worse than none: merging it over the built-in one
        # would hand this company the reference installation's plants.
        return Result(
            fixture("Profile"), Origin.MODELLED, "fixture:Profile",
            note="an uploaded profile was ignored, it has no "
                 + ", ".join(missing) + ". Using the reference installation",
        )
    return Result(fixture("Profile"), Origin.MODELLED, "fixture:Profile",
                  note="reference installation, not this company's own master data")


def profile() -> dict:
    """The engines want a plain dict. profile_result() carries the provenance."""
    return profile_result().value  # type: ignore[return-value]


#: Hosts that serve a demonstration dataset rather than a company's records.
MOCK_HOSTS = ("sandbox.api.sap.com",)


def is_mock_sap() -> bool:
    return any(h in (sap_s4.base_url() or "") for h in MOCK_HOSTS)


def _uploaded(entity: str, keep: Optional[Callable[[dict], bool]]) -> Optional[Result]:
    """The company's own file, if one was uploaded for this entity.

    Real company data that was uploaded rather than pulled outranks a fixture:
    it is genuine, just not live. Hence CACHED. A file the uploader declared as
    generated stays MODELLED, because calling it cached would launder it.
    """
    try:
        from core import store
        u = store.latest_upload(entity)
    except Exception:                                            # noqa: BLE001
        return None
    if not u:
        return None
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


def pull(
    fixture_entity: str,
    sap_service: str,
    sap_entity: str,
    params: Optional[Dict] = None,
    keep: Optional[Callable[[dict], bool]] = None,
) -> Result:
    """One read path shared by every read tool."""
    # A public sandbox is a mock. The company's own uploaded figures are real,
    # just not live, so they outrank a demo system carrying somebody else's
    # materials. A genuine S/4HANA tenant still outranks an upload, which is
    # why this turns on the base URL rather than on a flag.
    if is_mock_sap():
        own = _uploaded(fixture_entity, keep)
        if own is not None:
            return own

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

    own = _uploaded(fixture_entity, keep)
    if own is not None:
        return own

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


def fx_rate() -> Optional[int]:
    """USD to IDR from references/fx-rate.md, or None when it is not written."""
    r = rules.whole("usd_idr", 0)
    return r or None


def _to_idr(amount: float, currency: Optional[str]) -> Optional[int]:
    """Only currencies we hold a written rate for. The rest stay absent."""
    if currency == "IDR":
        return int(round(amount))
    if currency == "USD" and fx_rate():
        return int(round(amount * fx_rate()))
    return None


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
            # Ordered-on is what makes a lead time measurable. The header
            # has always carried it and the joined row dropped it, so every
            # lead time in the system had to be assumed.
            "PurchaseOrderDate": sap_date(head.get("PurchaseOrderDate")),
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
            # Allocation needs units, not only value.
            "OrderQuantity": float(it.get("RequestedQuantity") or 0),
            "BaseUnit": it.get("RequestedQuantityUnit"),
            "Currency": it.get("TransactionCurrency") or head.get("TransactionCurrency"),
            "RequestedDeliveryDate": sap_date(head.get("RequestedDeliveryDate")),
            "Customer": head.get("SoldToParty"),
        })
    return out


def _derived_alternate_sources(top: str = "200") -> List[dict]:
    """Who else has supplied this material, priced from what they charged.

    API_PURCHASING_INFO_RECORD_SRV is 403 on the free sandbox, so the list of
    approved sources cannot be read. It can be earned instead: a supplier who
    has delivered this material before is an alternate source by evidence
    rather than by master data, and the purchase order carries what they
    charged and how long they took.

    What is NOT derivable stays absent. TKDN is an Indonesian regulatory
    calculation that no SAP field holds, so tkdn_after is None and Kira rules
    on it knowing that, rather than on a number invented here.
    """
    rows = _joined_purchase_orders(top)
    heads = {h["PurchaseOrder"]: h for h in
             _sap_rows("API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrder", {"$top": top})}
    items = {(i.get("PurchaseOrder"), i.get("PurchaseOrderItem")): i for i in
             _sap_rows("API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrderItem",
                       {"$top": str(int(top) * 3)})}

    # One pass to the first item of each order. This was a linear search
    # inside a loop over every order line, which on 600 orders was a million
    # comparisons per read and the read happens more than once.
    first_item: Dict[str, dict] = {}
    for (po, _line), it in items.items():
        first_item.setdefault(po, it)

    as_of = date.fromisoformat(str(profile()["AsOfDate"])[:10])
    by_material: Dict[str, List[dict]] = {}
    for r in rows:
        head = heads.get(r["PurchaseOrder"], {})
        ordered = sap_date(head.get("PurchaseOrderDate"))
        lead = None
        if ordered and r["RevisedDeliveryDate"]:
            lead = (date.fromisoformat(r["RevisedDeliveryDate"])
                    - date.fromisoformat(ordered)).days
        item = first_item.get(r["PurchaseOrder"], {})
        by_material.setdefault(r["Material"], []).append({
            "Supplier": r["Supplier"],
            "Quantity": float(r["OrderQuantity"] or 0),
            "UnitPrice": float(item.get("NetPriceAmount") or 0),
            "Currency": item.get("DocumentCurrency"),
            "LeadDays": lead if lead and lead > 0 else None,
        })

    out: List[dict] = []
    for material, seen in by_material.items():
        priced = [s for s in seen if s["UnitPrice"] > 0]
        if not priced:
            continue
        floor = min(s["UnitPrice"] for s in priced)
        # One row per supplier, cheapest first, so option ids read in the order
        # a buyer would consider them.
        best: Dict[str, dict] = {}
        for s in sorted(priced, key=lambda x: x["UnitPrice"]):
            if s["Supplier"] and s["Supplier"] not in best:
                best[s["Supplier"]] = s
        for n, (supplier, s) in enumerate(best.items()):
            out.append({
                "id": f"{material}-{n + 1}",
                "label": f"Supplier {supplier}",
                "Material": material,
                "Supplier": supplier,
                "Quantity": s["Quantity"],
                "UnitPrice": s["UnitPrice"],
                "Currency": s["Currency"],
                "LeadDays": s["LeadDays"],
                # What this source costs over the cheapest one on record, in
                # the document's own currency. Not converted: an exchange rate
                # nobody stated is the kind of number this system refuses.
                "ExtraCost": round((s["UnitPrice"] - floor) * s["Quantity"], 2),
                # Converted at the written rate, which carries its own date.
                # A rupiah figure on an unstated rate is what used to keep
                # this None, and a stated rate fixes that rather than hiding
                # it: the rate and its date travel with the number.
                "ExtraCostIDR": _to_idr((s["UnitPrice"] - floor) * s["Quantity"],
                                        s["Currency"]),
                "FxRate": fx_rate() if s["Currency"] == "USD" else None,
                "FxAsOf": rules.text("fx_as_of") if s["Currency"] == "USD" else None,
                # Order today, arrive after the lead time this supplier has
                # actually run on its own purchase orders.
                "ArrivalDate": (as_of + timedelta(days=int(s["LeadDays"]))).isoformat()
                               if s["LeadDays"] else None,
                "TkdnAfterPct": None,
                # Not on the purchase order. Unknown origin is treated as
                # imported downstream, which is the recoverable error: an
                # extra five days of cover beats an unplanned stockout.
                "Origin": None,
                # A supplier who has already delivered this material is
                # qualified for it. That evidence is the whole basis of this
                # list, so there is nothing to approve again.
                "QualificationDays": 0,
            })
    return out


#: How long a joined SAP read is reused. Kira asks for the option list once
#: per option, so a 108-option handling made 108 joined reads of the same
#: three entities. Short enough that an operator who uploads a file sees it
#: take effect within a minute, long enough that one handling reads once.
SOURCES_CACHE_SECONDS = 60
_sources_memo: Optional[Tuple[float, Result]] = None


def forget_alternate_sources() -> None:
    """Drop the cache. Called after an upload, and by self-checks."""
    global _sources_memo
    _sources_memo = None


def _all_alternate_sources() -> Result:
    global _sources_memo
    now = time.monotonic()
    if _sources_memo and now - _sources_memo[0] < SOURCES_CACHE_SECONDS:
        return _sources_memo[1]
    got = pull("AlternateSource", "API_PURCHASING_INFO_RECORD_SRV",
               "A_PurchasingInfoRecord", {"$top": "200"})
    _sources_memo = (now, got)
    return got


def alternate_sources(material: Optional[str] = None) -> Result:
    """Every supply option, or one material's.

    One path, because Kira used to read the fixture while Clint read SAP, and
    that is why a live option id came back to the model as unknown. Filtering
    happens here rather than in the read, so asking for one material does not
    cost another round trip.
    """
    full = _all_alternate_sources()
    if material is None:
        return full
    return Result([r for r in (full.value or []) if r.get("Material") == material],
                  full.origin, full.source, full.fetched_at, full.note)


def alternate_source(option_id: str) -> Optional[dict]:
    """One option by id, from wherever the options actually come from."""
    return next((o for o in (alternate_sources().value or [])
                 if o.get("id") == option_id), None)


#: Reads that need more than one SAP entity to make one row.
JOINS = {
    "PurchaseOrder": _joined_purchase_orders,
    "BillOfMaterial": _joined_bom,
    "SalesOrder": _joined_sales_orders,
    "AlternateSource": _derived_alternate_sources,
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


def demo() -> None:
    """The precedence rule, which decides what every figure in the system is."""
    # A sandbox is a mock, so the company's own file outranks it. A real
    # tenant would not, which is why this turns on the host.
    assert "sandbox.api.sap.com" in MOCK_HOSTS[0]

    from core import store

    before = pull("MaterialStock", "API_MATERIAL_STOCK_SRV", "A_MatlStkInAcctMod",
                  {"$top": "3"})
    store.save_upload("MaterialStock", "company.csv",
                      [{"Material": "M-1", "Plant": "P1",
                        "MatlWrhsStkQtyInMatlBaseUnit": 1.0}], "ops@example.com")
    after = pull("MaterialStock", "API_MATERIAL_STOCK_SRV", "A_MatlStkInAcctMod",
                 {"$top": "3"})

    if is_mock_sap():
        assert after.origin is Origin.CACHED, after.origin
        assert after.trusted, "the company's own records are real, just not live"
        assert after.value[0]["Material"] == "M-1", after.value
        print(f"  upload beats a mock SAP: {before.origin.value} -> {after.origin.value} ✓")
    else:
        print("  not pointed at a mock, so the upload rule was not exercised")

    # A file declared as generated must not be laundered into CACHED.
    store.save_upload("SalesOrder", "sample.csv", [{"Material": "M-1"}],
                      "ops@example.com", synthetic=True)
    gen = pull("SalesOrder", "API_SALES_ORDER_SRV", "A_SalesOrder", {"$top": "3"})
    if is_mock_sap():
        assert gen.origin is Origin.MODELLED and not gen.trusted, gen.origin
        print("  a file declared as generated stays modelled ✓")

    # The profile is the one entity that used to ignore an upload, which meant
    # every installation was judged against the reference company's TKDN
    # position and measured from its plant coordinates.
    forget_alternate_sources()
    base = profile_result()
    assert base.origin is Origin.MODELLED, base.origin
    assert "Reference" in base.value["Company"], base.value["Company"]

    store.save_upload("Profile", "kpn-profile.csv", [
        {"Company": "PT Contoh Presisi", "AsOfDate": "2026-10-15",
         "TkdnCurrentPct": 44.0, "TkdnContractFloorPct": 40.0,
         "code": "CKR1", "kind": "plant", "name": "Cikarang",
         "lat": -6.2608, "lon": 107.1526},
    ], "ops@example.com")
    own = profile_result()
    assert own.origin is Origin.CACHED and own.trusted, own.brief()
    assert own.value["Company"] == "PT Contoh Presisi", own.value
    assert [f["code"] for f in own.value["Facilities"]] == ["CKR1"], own.value
    assert "KRW1" not in str(own.value), "the reference installation's plants leaked through"
    print(f"  profile follows the upload: {base.value['Company']} -> "
          f"{own.value['Company']}, {len(own.value['Facilities'])} facility ✓")

    # Half a profile must be refused outright. Merging it would hand this
    # company the reference installation's plants and call them its own.
    store.save_upload("Profile", "partial.csv",
                      [{"Company": "PT Setengah"}], "ops@example.com")
    half = profile_result()
    assert half.origin is Origin.MODELLED, half.brief()
    assert half.value["Company"] == base.value["Company"], half.value
    assert "ignored" in half.note and "TkdnCurrentPct" in half.note, half.note
    print(f"  and refuses half of one: {half.note[:58]}... ✓")

    print("fetcher ok")


if __name__ == "__main__":
    # This check writes uploads, so it must not touch the operator's record.
    from core.config import fixtures_only

    fixtures_only(__file__, "SIGAP_FETCHER_CHECK")
    demo()
