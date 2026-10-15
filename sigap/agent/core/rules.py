"""The written rules, read as data.

references/ holds the rules this system enforces: the TKDN floor, the LARTAS
lead time, the holiday calendar, the port dwell figure, the operating targets,
the exchange rate. They live in Markdown because an operations manager has to
be able to argue with them, and they are load-bearing because the alternative
is a constant in a Python file that nobody reviewed.

This sits in core/ rather than in tools/compliance.py because the rules are an
input to the whole system, not a detail of one agent. Kira reads the TKDN
floor, the fetcher reads the exchange rate, the planner reads the service
level. Keeping it in compliance.py meant the fetcher could not read a
parameter without importing a tool that imports the fetcher.
"""
from __future__ import annotations

import pathlib
from datetime import date
from typing import Dict, FrozenSet, Optional

REFERENCES = pathlib.Path(__file__).resolve().parent.parent.parent / "references"


def pack() -> Dict[str, str]:
    """Every rule document, keyed by filename stem.

    Globbed rather than listed: a document added to references/ and not added
    to a tuple in here is a rule nobody enforces, and the list fell out of
    date the first time one was written.
    """
    return {f.stem: f.read_text() for f in sorted(REFERENCES.glob("*.md"))}


def params(p: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """`key: value` lines from the Parameters block of each document.

    The documents have to be load-bearing, not decorative. If the written
    floor says 40 and the code says 40 in its own constant, the day somebody
    edits the document is the day the two quietly disagree, and the rule that
    gets enforced is the one nobody reviewed.
    """
    out: Dict[str, str] = {}
    for text in (p if p is not None else pack()).values():
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


def holidays(p: Optional[Dict[str, str]] = None) -> FrozenSet[str]:
    """National holidays from the calendar document, as ISO date strings.

    A permit that takes ten working days does not take ten working days across
    Idul Fitri. Without these, every licence estimate in March 2027 is wrong
    in the one direction that causes a stockout.
    """
    text = (p if p is not None else pack()).get("holiday-calendar", "")
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 10 and line[4] == "-" and line[7] == "-":
            try:
                out.add(date.fromisoformat(line[:10]).isoformat())
            except ValueError:
                continue
    return frozenset(out)


def _number(key: str, default, cast):
    """A written parameter, or the default. A fallback that silently differs
    from the written rule is worse than no fallback, so the caller is given
    the default rather than a guess dressed as a reading."""
    v = params().get(key)
    if v is None:
        return default
    try:
        return cast(v)
    except ValueError:
        return default


def number(key: str, default: float = 0.0) -> float:
    return _number(key, default, float)


def whole(key: str, default: int = 0) -> int:
    return _number(key, default, lambda s: int(float(s)))


def text(key: str, default: str = "") -> str:
    return params().get(key, default)


def demo() -> None:
    p = pack()
    assert len(p) >= 7, f"the rule pack looks thin: {sorted(p)}"
    ps = params(p)

    # The numbers every other module now depends on.
    for k in ("contract_floor_pct", "new_origin_working_days",
              "priok_import_dwell_days", "service_level_z", "min_cover_days",
              "usd_idr", "fx_as_of"):
        assert ps.get(k), f"{k} is not written down"

    assert whole("new_origin_working_days") == 10, whole("new_origin_working_days")
    assert number("service_level_z") == 1.65, number("service_level_z")
    assert whole("usd_idr") > 10_000, whole("usd_idr")

    # An unwritten key returns the caller's default, not a zero that looks
    # like a reading.
    assert whole("not_a_real_parameter", 7) == 7

    cal = holidays(p)
    assert len(cal) > 10, f"the holiday calendar looks empty: {len(cal)}"
    assert "2027-03-19" in cal or any(d.startswith("2027-03") for d in cal), sorted(cal)[:5]

    print(f"  {len(p)} documents, {len(ps)} parameters, {len(cal)} holidays")
    print(f"  TKDN floor {ps['contract_floor_pct']}%, service level z "
          f"{ps['service_level_z']}, USD {ps['usd_idr']} as of {ps['fx_as_of']}")
    print("rules ok")


if __name__ == "__main__":
    demo()
