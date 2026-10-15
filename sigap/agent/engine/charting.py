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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: What a chart may be. Deliberately few: these answer the questions this
#: domain actually asks, and a kind nobody can name is a kind nobody can read.
KINDS = ("bar", "line", "scatter")

#: A bar per row stops being a chart somewhere around a dozen and becomes a
#: wall. The same ceiling the domain charts already use.
DEFAULT_LIMIT = 12
MAX_LIMIT = 40

#: Where a row keeps its unit of measure, in the order we look.
UNIT_KEYS = ("unit", "BaseUnit", "uom")


@dataclass
class Chart:
    kind: str
    title: str
    x: str
    y: str
    points: List[dict] = field(default_factory=list)
    unit: Optional[str] = None
    series: Optional[str] = None
    total_rows: int = 0
    truncated: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "title": self.title, "x": self.x, "y": self.y,
            "series": self.series, "unit": self.unit, "points": self.points,
            "total_rows": self.total_rows, "truncated": self.truncated,
            "note": self.note,
        }


@dataclass
class Refusal:
    reason: str
    available: Optional[List[str]] = None


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


def build(rows: Any, kind: str, x: str, y: str,
          title: str = "", series: Optional[str] = None,
          limit: int = DEFAULT_LIMIT) -> Chart | Refusal:
    """Arrange rows into a chart, or say why they cannot be one."""
    if kind not in KINDS:
        return Refusal(f"'{kind}' is not a chart this system draws",
                       available=list(KINDS))
    if not isinstance(rows, list) or not rows:
        return Refusal("that finding is not a list of rows, so there is nothing "
                       "to chart")
    usable = [r for r in rows if isinstance(r, dict)]
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
    # lies without a single wrong number in it.
    unit, all_units = _units([r for r, _ in plottable])
    if len(all_units) > 1:
        return Refusal(
            f"those rows mix units ({', '.join(all_units)}), so one axis would "
            f"put them on the same scale. Chart one unit at a time, or chart a "
            f"column that is already comparable across them")

    cap = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    # Largest first for a comparison, chronological for a series: a line read
    # out of order is not a trend, and a bar chart in arbitrary order hides
    # the thing it was drawn to show.
    if kind == "line":
        plottable.sort(key=lambda rv: str(rv[0].get(x)))
    else:
        plottable.sort(key=lambda rv: -rv[1])
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
        notes.append(f"showing {len(shown)} of {len(plottable)} rows, "
                     f"{'largest' if kind != 'line' else 'earliest'} first")
    skipped = len(valued) - len(plottable)
    if skipped:
        notes.append(f"{skipped} row(s) had no number in '{y}' and are not drawn")

    return Chart(kind=kind, title=title or f"{y} by {x}", x=x, y=y,
                 points=points, unit=unit, series=series,
                 total_rows=len(plottable), truncated=dropped,
                 note="; ".join(notes))


def demo() -> None:
    stock = [
        {"material": "M-4471", "plant": "KRW1", "days_left": 9.1, "unit": "TON"},
        {"material": "M-4472", "plant": "KRW1", "days_left": 21.4, "unit": "TON"},
        {"material": "M-4478", "plant": "SBY1", "days_left": 4.0, "unit": "TON"},
    ]

    c = build(stock, "bar", "material", "days_left", title="Cover in days")
    assert isinstance(c, Chart), c
    assert [p["x"] for p in c.points] == ["M-4472", "M-4471", "M-4478"], c.points
    assert c.unit == "TON" and c.total_rows == 3 and c.truncated == 0
    print(f"  bar: {[ (p['x'], p['y']) for p in c.points ]} in {c.unit}")

    # Mixed units must be refused outright. This is the one that would have
    # produced a plausible, persuasive, wrong picture.
    mixed = build(stock + [{"material": "M-1172", "days_left": 18.0, "unit": "PC"}],
                  "bar", "material", "days_left")
    assert isinstance(mixed, Refusal) and "mix units" in mixed.reason, mixed
    print(f"  mixed units refused: {mixed.reason[:58]}...")

    # A text column on y is a category error, and the refusal names the columns
    # so the caller can pick a real one rather than guessing again.
    bad = build(stock, "bar", "material", "plant")
    assert isinstance(bad, Refusal) and "no numbers" in bad.reason, bad
    assert "days_left" in (bad.available or []), bad.available

    assert isinstance(build(stock, "pie", "material", "days_left"), Refusal)
    assert isinstance(build(stock, "bar", "nope", "days_left"), Refusal)
    assert isinstance(build([], "bar", "a", "b"), Refusal)
    assert isinstance(build("not rows", "bar", "a", "b"), Refusal)

    # A line is chronological, never sorted by size.
    series = [{"on": "2026-09-03", "qty": 5}, {"on": "2026-09-01", "qty": 9},
              {"on": "2026-09-02", "qty": 7}]
    line = build(series, "line", "on", "qty")
    assert [p["x"] for p in line.points] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    print(f"  line stays in date order: {[p['x'][-5:] for p in line.points]}")

    # The ceiling holds, and says how much it is not showing.
    many = [{"m": f"M-{i}", "v": i} for i in range(60)]
    capped = build(many, "bar", "m", "v", limit=99)
    assert len(capped.points) == MAX_LIMIT, len(capped.points)
    assert capped.truncated == 60 - MAX_LIMIT and "showing" in capped.note
    print(f"  60 rows capped to {len(capped.points)}: {capped.note}")

    # Rows with a missing number are counted, not silently dropped.
    holey = build(stock + [{"material": "M-9", "days_left": None, "unit": "TON"}],
                  "bar", "material", "days_left")
    assert "no number" in holey.note, holey.note

    print("charting ok")


if __name__ == "__main__":
    demo()
