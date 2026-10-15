"""Turning rows that are already on the board into a chart.

A chart is a presentation of numbers, so the same rule applies to it as to a
rupiah figure: the model may choose the view, and it may not produce the
values. Everything here takes rows a tool returned and arranges them. Nothing
here accepts a data point from a caller.

That constraint is not pedantry. A chart is more persuasive than a number, so
a chart that quietly mixes tonnes with pieces, or draws modelled data in the
same ink as live data, is a more effective way to mislead than any sentence.
The refusals below are the whole point of the file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: What a chart may be. Deliberately few: these answer the questions this
#: domain actually asks, and a kind nobody can name is a kind nobody can read.
KINDS = ("bar", "line", "scatter")

#: A bar per row stops being a chart somewhere around a dozen and becomes a
#: wall. The same ceiling the domain charts already use.
DEFAULT_LIMIT = 12
MAX_LIMIT = 40

@dataclass
class Refusal:
    reason: str
    available: Optional[List[str]] = None


#: Where a row keeps its unit of measure, in the order we look.
UNIT_KEYS = ("unit", "BaseUnit", "uom")

#: Columns whose NAME already declares what they are measured in. A quantity
#: is in the row's unit, so tonnes and pieces cannot share an axis. Days of
#: cover are days whatever the material is made of, a penalty is rupiah, and a
#: percentage is a percentage. Refusing those for "mixed units" was a false
#: refusal, and it blocked the most useful chart in the system: which material
#: runs out first, across every material in the plant.
DECLARED_UNITS = {
    "days": "days", "day": "days", "hours": "hours", "hour": "hours",
    "pct": "%", "percent": "%",
    "idr": "Rp", "rp": "Rp",
}


def declared_unit(column: str) -> Tuple[bool, Optional[str]]:
    """Whether this column carries its own unit, and which.

    Token match rather than a suffix test, so cover_days, days_left and
    penalty_idr are all caught while DailyConsumption and OrderQuantity are
    correctly left to the row's unit.
    """
    for token in re.split(r"[^a-z0-9]+", column.lower()):
        if token in DECLARED_UNITS:
            return True, DECLARED_UNITS[token]
    return False, None


#: Keys a dict-shaped finding tends to keep its rows under. Most tools here
#: return {"rows": [...]} or {"orders": [...]} with counts beside them, and a
#: chart tool that only accepted a bare list could reach almost none of them.
ROW_KEYS = ("rows", "orders", "options", "combinations", "positions", "items",
            "points", "findings", "matches", "suppliers")


def _candidates(value: dict, prefix: str = "", depth: int = 2) -> Dict[str, list]:
    """Every list of row-shaped dicts inside this object, by dotted path."""
    found: Dict[str, list] = {}
    for k, v in value.items():
        path = f"{prefix}{k}"
        if isinstance(v, list) and v and all(isinstance(r, dict) for r in v):
            found[path] = v
        elif isinstance(v, dict) and depth > 1:
            found.update(_candidates(v, f"{path}.", depth - 1))
    return found


def rows_in(value: Any, path: Optional[str] = None) -> Any | Refusal:
    """The list of rows inside a finding, whatever shape it arrived in.

    Auto-detected when there is only one place it could be, because a path
    argument is one more thing to get wrong. When there is more than one it
    refuses and names them by dotted path, so the next attempt can say which:
    propose_allocation holds both `proposed.orders` and `by_date.orders`, and
    those are two different answers. Drawing the wrong one silently would
    attribute one plan's penalties to the other.
    """
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return Refusal("that finding is neither a list of rows nor an object "
                       "holding one")

    found = _candidates(value)
    if path:
        if path in found:
            return found[path]
        return Refusal(f"there is no list of rows at '{path}' in that finding",
                       available=sorted(found) or None)
    if not found:
        return Refusal("that finding holds no list of rows to chart")
    if len(found) == 1:
        return next(iter(found.values()))

    top = [k for k in found if "." not in k]
    preferred = [k for k in ROW_KEYS if k in top]
    if len(preferred) == 1:
        return found[preferred[0]]
    return Refusal("that finding holds more than one list of rows, so it is not "
                   "clear which to draw. Name one with `rows`",
                   available=sorted(found))


@dataclass
class Chart:
    kind: str
    title: str
    x: str
    y: str
    points: List[dict] = field(default_factory=list)
    unit: Optional[str] = None
    series: Optional[str] = None
    order: str = "highest"
    total_rows: int = 0
    truncated: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "title": self.title, "x": self.x, "y": self.y,
            "series": self.series, "unit": self.unit, "order": self.order,
            "points": self.points,
            "total_rows": self.total_rows, "truncated": self.truncated,
            "note": self.note,
        }


def _numeric(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _units(rows: Sequence[dict]) -> Tuple[Optional[str], List[str]]:
    """The one unit these rows share, and every unit found."""
    for key in UNIT_KEYS:
        found = sorted({str(r[key]) for r in rows
                        if isinstance(r, dict) and r.get(key)})
        if found:
            return (found[0] if len(found) == 1 else None), found
    return None, []


#: Which end of the data matters. It has to be the caller's choice: for a
#: penalty the biggest number is the story, and for days of cover the smallest
#: one is, so a single hardcoded direction is wrong half the time. It was
#: hardcoded to "highest", which produced a chart titled "thinnest first"
#: showing the thickest positions and silently dropping the nine most urgent.
ORDERS = ("highest", "lowest")


def build(rows: Any, kind: str, x: str, y: str,
          title: str = "", series: Optional[str] = None,
          limit: int = DEFAULT_LIMIT,
          order: str = "highest",
          rows_path: Optional[str] = None) -> Chart | Refusal:
    """Arrange rows into a chart, or say why they cannot be one."""
    if order not in ORDERS:
        return Refusal(f"'{order}' is not an order", available=list(ORDERS))
    if kind not in KINDS:
        return Refusal(f"'{kind}' is not a chart this system draws",
                       available=list(KINDS))
    found = rows_in(rows, rows_path)
    if isinstance(found, Refusal):
        return found
    if not found:
        return Refusal("that finding holds no rows, so there is nothing to chart")
    usable = [r for r in found if isinstance(r, dict)]
    if not usable:
        return Refusal("that finding holds no rows with named fields")

    columns = sorted({k for r in usable for k in r})
    for axis, name in (("x", x), ("y", y)):
        if name not in columns:
            return Refusal(f"there is no '{name}' in that finding to put on {axis}",
                           available=columns)
    if series and series not in columns:
        return Refusal(f"there is no '{series}' in that finding to split series on",
                       available=columns)

    # y has to be a number. Charting a text column is the mistake that turns
    # "which supplier" into a bar of height 1 next to another bar of height 1.
    valued = [(r, _numeric(r.get(y))) for r in usable]
    plottable = [(r, v) for r, v in valued if v is not None]
    if not plottable:
        return Refusal(f"'{y}' holds no numbers in that finding, so it cannot be "
                       f"an axis", available=columns)

    # One axis, one unit. Tonnes and pieces on the same scale is a chart that
    # lies without a single wrong number in it. Unless the column says what it
    # is measured in, in which case the row's unit is beside the point.
    own, own_unit = declared_unit(y)
    if own:
        unit, all_units = own_unit, []
    else:
        unit, all_units = _units([r for r, _ in plottable])
        if len(all_units) > 1:
            return Refusal(
                f"those rows mix units ({', '.join(all_units)}), so one axis would "
                f"put them on the same scale. Chart one unit at a time, or chart a "
                f"column that is already comparable across them, such as one "
                f"measured in days or in rupiah")

    cap = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    # Largest first for a comparison, chronological for a series: a line read
    # out of order is not a trend, and a bar chart in arbitrary order hides
    # the thing it was drawn to show.
    if kind == "line":
        plottable.sort(key=lambda rv: str(rv[0].get(x)))
    else:
        plottable.sort(key=lambda rv: rv[1] if order == "lowest" else -rv[1])
    shown = plottable[:cap]

    points = []
    for r, v in shown:
        p = {"x": str(r.get(x)), "y": v}
        if series:
            p["series"] = str(r.get(series))
        points.append(p)

    dropped = len(plottable) - len(shown)
    notes = []
    if dropped:
        # Which end was KEPT, not merely which way it is sorted. A reader who
        # cannot tell is a reader who does not know what was dropped.
        kept = ("earliest" if kind == "line"
                else "smallest" if order == "lowest" else "largest")
        notes.append(f"showing the {kept} {len(shown)} of {len(plottable)} rows")
    skipped = len(valued) - len(plottable)
    if skipped:
        notes.append(f"{skipped} row(s) had no number in '{y}' and are not drawn")

    # Two bars with the same label is legitimate, two customer orders from one
    # customer for instance, but a reader will assume one bar per label unless
    # told. Not a refusal: the alternative is summing rows nobody asked to sum.
    labels = [p["x"] for p in points]
    if len(set(labels)) < len(labels):
        notes.append(f"'{x}' repeats, so some rows share a label and are drawn "
                     f"as separate bars rather than added together")

    return Chart(kind=kind, title=title or f"{y} by {x}", x=x, y=y, order=order,
                 points=points, unit=unit, series=series,
                 total_rows=len(plottable), truncated=dropped,
                 note="; ".join(notes))


def demo() -> None:
    stock = [
        {"material": "M-4471", "plant": "KRW1", "qty": 84.0, "days_left": 9.1, "unit": "TON"},
        {"material": "M-4472", "plant": "KRW1", "qty": 210.0, "days_left": 21.4, "unit": "TON"},
        {"material": "M-4478", "plant": "SBY1", "qty": 12.0, "days_left": 4.0, "unit": "TON"},
    ]

    c = build(stock, "bar", "material", "qty", title="Stock on hand")
    assert isinstance(c, Chart), c
    assert [p["x"] for p in c.points] == ["M-4472", "M-4471", "M-4478"], c.points
    assert c.unit == "TON" and c.total_rows == 3 and c.truncated == 0
    print(f"  quantity takes the row unit: {c.unit}")

    # --- mixed units, the refusal this file exists for -------------------
    mixed = stock + [{"material": "M-1172", "qty": 9590.0, "unit": "PC"}]
    bad = build(mixed, "bar", "material", "qty")
    assert isinstance(bad, Refusal) and "mix units" in bad.reason, bad
    print(f"  mixed units refused: {bad.reason[:52]}...")

    # ...but a column that names its own unit is not in the row's unit, and
    # refusing it was a false refusal that blocked the most useful chart in
    # the system: which material runs out first, across all of them.
    free = build(mixed, "bar", "material", "days_left", order="lowest")
    assert isinstance(free, Chart), free
    assert free.unit == "days", free.unit
    assert [p["x"] for p in free.points] == ["M-4478", "M-4471", "M-4472"], free.points
    print(f"  days_left charts across TON and PC together, unit {free.unit} ✓")
    assert declared_unit("penalty_idr") == (True, "Rp")
    assert declared_unit("demand_variability_pct") == (True, "%")
    assert declared_unit("OrderQuantity") == (False, None)

    # --- which end matters is the caller's -------------------------------
    # Hardcoding "highest" produced a chart titled "thinnest first" showing
    # the thickest rows and dropping the urgent ones.
    many = [{"m": f"M-{i}", "cover_days": float(i)} for i in range(1, 31)]
    low = build(many, "bar", "m", "cover_days", limit=5, order="lowest")
    high = build(many, "bar", "m", "cover_days", limit=5, order="highest")
    assert [p["y"] for p in low.points] == [1, 2, 3, 4, 5], low.points
    assert [p["y"] for p in high.points] == [30, 29, 28, 27, 26], high.points
    assert "smallest 5 of 30" in low.note, low.note
    assert "largest 5 of 30" in high.note, high.note
    print(f"  lowest keeps {[p['y'] for p in low.points]}, "
          f"highest keeps {[p['y'] for p in high.points]} ✓")
    assert isinstance(build(many, "bar", "m", "cover_days", order="sideways"), Refusal)

    # --- a finding that is an object, not a list -------------------------
    # Most tools here return {"rows": [...]} with counts beside it. A chart
    # tool that only took a bare list could reach almost none of them.
    wrapped = {"reviewed": 53, "order_now": 15, "rows": stock}
    inner = build(wrapped, "bar", "material", "qty")
    assert isinstance(inner, Chart) and inner.total_rows == 3, inner
    print(f"  reached rows inside an object of {len(wrapped)} keys ✓")

    # Two candidate lists must refuse and name them, because picking one
    # silently is how a chart gets drawn from the wrong half of an answer.
    two = build({"rows": stock, "orders": [{"a": 1}]}, "bar", "material", "qty")
    assert isinstance(two, Refusal) and "more than one list" in two.reason, two
    assert two.available == ["orders", "rows"], two.available
    print(f"  two row lists refused, naming {two.available} ✓")

    # --- the rest of the refusals ----------------------------------------
    text_y = build(stock, "bar", "material", "plant")
    assert isinstance(text_y, Refusal) and "no numbers" in text_y.reason
    assert "days_left" in (text_y.available or []), text_y.available
    assert isinstance(build(stock, "pie", "material", "qty"), Refusal)
    assert isinstance(build(stock, "bar", "nope", "qty"), Refusal)
    assert isinstance(build([], "bar", "a", "b"), Refusal)
    assert isinstance(build("not rows", "bar", "a", "b"), Refusal)
    assert isinstance(build({"total": 3}, "bar", "a", "b"), Refusal)

    # A line is chronological, never sorted by size, whatever `order` says.
    series = [{"on": "2026-09-03", "qty": 5}, {"on": "2026-09-01", "qty": 9},
              {"on": "2026-09-02", "qty": 7}]
    line = build(series, "line", "on", "qty", order="lowest")
    assert [p["x"] for p in line.points] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    print(f"  line stays in date order: {[p['x'][-5:] for p in line.points]}")

    capped = build([{"m": f"M-{i}", "v": i} for i in range(60)], "bar", "m", "v",
                   limit=99)
    assert len(capped.points) == MAX_LIMIT and capped.truncated == 60 - MAX_LIMIT
    print(f"  60 rows capped to {len(capped.points)}: {capped.note}")

    holey = build(stock + [{"material": "M-9", "qty": None, "unit": "TON"}],
                  "bar", "material", "qty")
    assert "no number" in holey.note, holey.note

    print("charting ok")


if __name__ == "__main__":
    demo()
