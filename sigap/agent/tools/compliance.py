"""Kira's tools (Rules).

Reads the rule pack in references/ rather than from the model's memory. A
rejection from this file is final: cost arguments cannot overturn it.

Two things used to go wrong here and both are fixed by delegating:

  - the rules were read by a private parser in this file, so no other module
    could reach a written parameter. They now come from core/rules.py.
  - this file computed its own effective arrival date and the costing engine
    ignored it. The date now comes from engine/arrival.py, which is the one
    place that answers that question, and it travels on the ruling.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from core import rules
from core.provenance import Origin, Result
from core.registry import register
from engine.arrival import Estimate, effective_arrival
from tools.fetcher import alternate_source, profile

# Used only when the rule pack does not state it. A fallback that silently
# differs from the written rule is worse than no fallback, so it is reported.
LARTAS_WORKING_DAYS_NEW_ORIGIN = 10


def arrival_for(option: dict, dwell_days: Optional[int] = None) -> Optional[Estimate]:
    """When this option actually lands, with every correction named.

    Public because Milo needs the same answer and a second implementation is
    how the first one stopped being true.
    """
    booked = option.get("ArrivalDate")
    if not booked:
        return None

    # Unknown origin is treated as imported. The purchase order does not
    # carry a country, and the optimistic default is the one that empties a
    # plant: five days of extra cover is recoverable, a stockout is not.
    origin = option.get("Origin")
    imported = origin != "ID"
    return effective_arrival(
        date.fromisoformat(str(booked)[:10]),
        permit_days=(rules.whole("new_origin_working_days",
                                 LARTAS_WORKING_DAYS_NEW_ORIGIN)
                     if option.get("NewOrigin") else 0),
        permit_reason=f"LARTAS, new origin {option.get('Origin')}",
        qualification_days=int(option.get("QualificationDays") or 0),
        dwell_days=(dwell_days if dwell_days is not None
                    else rules.whole("priok_import_dwell_days") if imported else 0),
        dwell_reason=("port dwell" if origin else
                      "port dwell, origin unknown so assumed imported"),
        holidays=rules.holidays(),
    )


@register(
    "check_local_constraints", "compliance",
    "Test one supply option against TKDN, LARTAS, contract clauses, and the holiday "
    "calendar. Returns allowed/blocked with a reason that names the rule and the "
    "numbers, plus the effective arrival date once the import permit, supplier "
    "qualification and port dwell are counted. A rejection here is final and must "
    "not be overridden on cost.",
    {"option_id": {"type": "string", "description": "option id, e.g. 'A'"}},
    ["option_id"],
)
def check_local_constraints(option_id: str) -> Result:
    pack = rules.pack()
    p = profile()
    option = alternate_source(option_id)
    if option is None:
        return Result(None, Origin.MISSING, "references/",
                      note=f"unknown option '{option_id}'")

    reasons: List[str] = []
    allowed = True

    # The written rule outranks the scenario profile. The profile describes
    # this company's contract; the reference describes the law behind it, and
    # where they differ the law is the one that gets enforced on us.
    floor = rules.number("contract_floor_pct", float(p["TkdnContractFloorPct"]))

    # --- TKDN ---
    # The rule: an option must not WORSEN the local-content position, and must
    # not push it below the contract floor when we are currently above it. A
    # company already below the floor does not thereby lose every option, what
    # is forbidden is making it worse.
    tkdn = option.get("TkdnAfterPct")
    current = p["TkdnCurrentPct"]
    if tkdn is not None:
        if tkdn < current - 0.05:                       # rounding tolerance
            allowed = False
            reasons.append(
                f"TKDN falls from {current}% to {tkdn}%"
                + (f", further below the {floor}% contract floor" if tkdn < floor
                   else f", breaching the {floor}% contract floor")
            )
        elif tkdn < floor <= current:
            allowed = False
            reasons.append(f"TKDN drops to {tkdn}%, contract floor {floor}%")
        elif tkdn >= floor > current:
            reasons.append(f"TKDN rises to {tkdn}%, back above the {floor}% floor")
    else:
        reasons.append("TKDN after this option is not known, no SAP field holds it")

    # --- Dates ---
    est = arrival_for(option)
    if est is not None and est.steps:
        reasons.append(est.explain())

    note = "" if pack else (
        "references/ is not written yet. TKDN and LARTAS were judged from fixture "
        "parameters rather than from the rule documents"
    )
    return Result(
        {
            "option_id": option_id,
            "allowed": allowed,
            "reason": "; ".join(reasons) if reasons else "no rule breached",
            "arrival_booked": est.booked.isoformat() if est else None,
            "arrival_effective": est.effective.isoformat() if est else None,
            "arrival": est.as_dict() if est else None,
            "tkdn_after": tkdn,
        },
        Origin.DERIVED if pack else Origin.MODELLED,
        "references/ (rule pack)" if pack else "fixture + built-in rules",
        note=note,
    )


def demo() -> None:
    # The rule documents have to drive the ruling, or they are decoration and
    # the enforced rule is whatever is hardcoded here.
    params = rules.params()
    assert params.get("contract_floor_pct"), "the TKDN floor is not written down"
    assert params.get("new_origin_working_days"), "the LARTAS lead time is not written down"
    print(f"  rule pack drives the ruling: floor {params['contract_floor_pct']}%, "
          f"LARTAS {params['new_origin_working_days']} working days, "
          f"{len(rules.holidays())} holidays")

    p = profile()
    assert p["TkdnCurrentPct"] < p["TkdnContractFloorPct"], \
        "the scenario assumes the company already sits below the floor"

    # An option that keeps TKDN where it is must NOT be rejected just for
    # being under the floor, that was the bug this check exists to catch.
    a = check_local_constraints("A").value
    assert a["allowed"] is True, a["reason"]

    # An option that actively worsens TKDN must be rejected.
    e = check_local_constraints("E").value
    assert e["allowed"] is False and "TKDN" in e["reason"], e

    # A new origin country delays arrival past its booked date, and the delay
    # is reported in a form a buyer can check rather than as one number.
    d = check_local_constraints("D").value
    assert d["arrival_effective"] > d["arrival_booked"], d
    assert "LARTAS" in d["reason"]
    assert d["arrival"]["slip_days"] > 0, d["arrival"]
    print(f"  option D: {d['arrival']['explain']}")

    # Qualification days used to be read by nobody. An option that needs
    # first-article approval must not be planned on its booked date.
    f = check_local_constraints("F").value
    assert f["arrival_effective"] > f["arrival_booked"], f
    assert any(s["reason"] == "supplier qualification" for s in f["arrival"]["steps"]), f
    print(f"  option F: {f['arrival']['explain']}")

    # A domestic option gets no dwell and no permit, so nothing is added.
    c = check_local_constraints("C").value
    assert c["arrival_effective"] == c["arrival_booked"], c

    assert check_local_constraints("ZZ").origin is Origin.MISSING
    print("compliance ok, keeps TKDN ✓ · worsens TKDN → blocked ✓ · "
          "permit, qualification and dwell all reach the date ✓")


if __name__ == "__main__":
    # The fixture options A..G are what this check reasons about. Pointed at
    # SAP, the options are whatever that tenant has supplied before, so the
    # check would be asserting on somebody else's purchase history.
    from core.config import fixtures_only

    fixtures_only(__file__, "SIGAP_COMPLIANCE_CHECK")
    demo()
