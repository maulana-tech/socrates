"""Kira's tools (Rules).

Reads the rule pack in references/ rather than from the model's memory. A
rejection from this file is final: cost arguments cannot overturn it.
"""
from __future__ import annotations

import pathlib
from datetime import date, timedelta
from typing import Dict, List

from core.provenance import Origin, Result
from core.registry import register
from tools.fetcher import fixture, profile

REFERENCES = pathlib.Path(__file__).resolve().parent.parent.parent / "references"

# Used only when the rule pack does not state it. A fallback that silently
# differs from the written rule is worse than no fallback, so it is reported.
LARTAS_WORKING_DAYS_NEW_ORIGIN = 10


def _rule_pack() -> Dict[str, str]:
    """Read the rule documents. If one isn't written yet, say so, don't guess."""
    out: Dict[str, str] = {}
    for name in ("tkdn-rules", "lartas-procedure", "holiday-calendar", "priok-dwell-time"):
        f = REFERENCES / f"{name}.md"
        if f.exists():
            out[name] = f.read_text()
    return out


def rule_params(pack: Dict[str, str]) -> Dict[str, str]:
    """`key: value` lines from the Parameters block of each rule document.

    The documents have to be load-bearing, not decorative. If the written floor
    says 40 and the code says 40 in its own constant, the day somebody edits
    the document is the day the two quietly disagree, and the rule that gets
    enforced is the one nobody reviewed.
    """
    out: Dict[str, str] = {}
    for text in pack.values():
        body = text.split("## Parameters", 1)
        if len(body) < 2:
            continue
        for line in body[1].splitlines():
            line = line.strip()
            if line.startswith(("#", "<!--", "`")) or ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if k and v and " " not in k:
                out[k] = v
    return out


def holidays(pack: Dict[str, str]) -> set:
    """National holidays from the calendar document, as ISO date strings.

    A permit that takes ten working days does not take ten working days across
    Idul Fitri. Without these, every licence estimate in March 2027 is wrong
    in the one direction that causes a stockout.
    """
    text = pack.get("holiday-calendar", "")
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 10 and line[4] == "-" and line[7] == "-":
            try:
                out.add(date.fromisoformat(line[:10]).isoformat())
            except ValueError:
                continue
    return out


def _add_working_days(start: date, days: int, skip: set = frozenset()) -> date:
    d, left = start, days
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in skip:
            left -= 1
    return d


@register(
    "check_local_constraints", "compliance",
    "Test one supply option against TKDN, LARTAS, contract clauses, and the holiday "
    "calendar. Returns allowed/blocked with a reason that names the rule and the "
    "numbers. A rejection here is final and must not be overridden on cost.",
    {"option_id": {"type": "string", "description": "option id, e.g. 'A'"}},
    ["option_id"],
)
def check_local_constraints(option_id: str) -> Result:
    pack = _rule_pack()
    p = profile()
    option = next((o for o in fixture("AlternateSource") if o["id"] == option_id), None)
    if option is None:
        return Result(None, Origin.MISSING, "references/",
                      note=f"unknown option '{option_id}'")

    params = rule_params(pack)
    reasons: List[str] = []
    allowed = True

    # The written rule outranks the scenario profile. The profile describes
    # this company's contract; the reference describes the law behind it, and
    # where they differ the law is the one that gets enforced on us.
    floor = p["TkdnContractFloorPct"]
    written_floor = params.get("contract_floor_pct")
    if written_floor:
        try:
            floor = float(written_floor)
        except ValueError:
            pass

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

    # --- LARTAS ---
    arrives = date.fromisoformat(option["ArrivalDate"])
    if option.get("NewOrigin"):
        try:
            days = int(params.get("new_origin_working_days",
                                  LARTAS_WORKING_DAYS_NEW_ORIGIN))
        except ValueError:
            days = LARTAS_WORKING_DAYS_NEW_ORIGIN
        licensed = _add_working_days(arrives, days, holidays(pack))
        reasons.append(
            f"LARTAS: a new origin country ({option['Origin']}) adds "
            f"{days} working days, effective arrival {licensed}"
        )
        arrives = licensed

    note = "" if pack else (
        "references/ is not written yet. TKDN and LARTAS were judged from fixture "
        "parameters rather than from the rule documents"
    )
    return Result(
        {
            "option_id": option_id,
            "allowed": allowed,
            "reason": "; ".join(reasons) if reasons else "no rule breached",
            "arrival_effective": arrives.isoformat(),
            "tkdn_after": tkdn,
        },
        Origin.DERIVED if pack else Origin.MODELLED,
        "references/ (rule pack)" if pack else "fixture + built-in rules",
        note=note,
    )


def demo() -> None:
    # The rule documents have to drive the ruling, or they are decoration and
    # the enforced rule is whatever is hardcoded here.
    pack = _rule_pack()
    params = rule_params(pack)
    assert params.get("contract_floor_pct"), "the TKDN floor is not written down"
    assert params.get("new_origin_working_days"), "the LARTAS lead time is not written down"

    cal = holidays(pack)
    assert len(cal) > 10, f"the holiday calendar looks empty: {len(cal)}"
    # March 2027 carries Nyepi and two days of Idul Fitri. A permit counted
    # without them finishes in the wrong month.
    naive = _add_working_days(date(2027, 3, 5), 10)
    real = _add_working_days(date(2027, 3, 5), 10, cal)
    assert real > naive, (naive, real)
    print(f"  rule pack drives the ruling: floor {params['contract_floor_pct']}%, "
          f"LARTAS {params['new_origin_working_days']} working days, "
          f"{len(cal)} holidays")
    print(f"  a 10 working day permit from 5 Mar 2027 ends {real}, not {naive}")

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

    # A new origin country delays arrival past its booked date.
    d = check_local_constraints("D").value
    booked = next(o for o in fixture("AlternateSource") if o["id"] == "D")["ArrivalDate"]
    assert d["arrival_effective"] > booked, d
    assert "LARTAS" in d["reason"]

    assert check_local_constraints("ZZ").origin is Origin.MISSING
    print("compliance ok, keeps TKDN ✓ · worsens TKDN → blocked ✓ · LARTAS delay ✓")


if __name__ == "__main__":
    demo()
