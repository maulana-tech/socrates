"""Drawing a finding, available to every agent.

The question this answers is a UX one. A specialist that has just read the
thinnest twelve stock positions and replies in prose has done the work and
hidden it: a bar chart of the same twelve rows is read in a second. So any
agent may draw what it found.

What no agent may do is supply the numbers. This tool takes a KEY into the
shared board and the names of two columns. The data is whatever the tool that
wrote that key returned, and the origin label travels with it, so a chart of
modelled figures cannot be drawn in the same ink as a chart of live ones.

That is the whole design. A chart is more persuasive than a sentence, which
makes it a better instrument for misleading somebody, so the model gets to
choose the view and never the values.
"""
from __future__ import annotations

from typing import Optional

from core import registry
from core.provenance import Origin, Result
from core.registry import UNIVERSAL, register
from engine.charting import DEFAULT_LIMIT, KINDS, ORDERS, Chart, build


@register(
    "chart_finding", UNIVERSAL,
    "Draw something already on the shared board as a chart, so the answer is read "
    "rather than parsed. Pass the board key of a finding you have ALREADY read, the "
    "kind of chart, and which two of its columns go on the axes. You cannot pass data: "
    "the figures come from the tool result under that key, and its origin label is "
    "carried onto the chart. Use it whenever an answer is a comparison across more "
    "than about four rows, or a movement over time. Prefer a chart AND one sentence "
    "reading it over a paragraph describing the numbers.",
    {
        "key": {"type": "string",
                "description": "board key of the finding, as shown in the board "
                               "summary, e.g. 'impact.get_material_stock'"},
        "kind": {"type": "string", "enum": list(KINDS),
                 "description": "bar to compare across rows, line for movement over "
                                "time, scatter to relate two numbers"},
        "x": {"type": "string", "description": "column for the horizontal axis"},
        "y": {"type": "string", "description": "numeric column for the vertical axis"},
        "title": {"type": ["string", "null"],
                  "description": "what the reader should take from it, in a few words"},
        "series": {"type": ["string", "null"],
                   "description": "optional column to split the rows into series"},
        "limit": {"type": ["integer", "null"],
                  "description": f"how many rows to draw. Default {DEFAULT_LIMIT}"},
        "rows": {"type": ["string", "null"],
                 "description": "only when a finding holds more than one list of "
                                "rows and the refusal asked which, e.g. "
                                "'proposed.orders'"},
        # A plain string with an enum, not a nullable one. The real model's
        # schema validator rejects an enum beside a union type outright:
        # "Enum value 'highest' does not match declared type ['string','null']".
        # Optional is expressed by staying out of `required`, not by allowing
        # null, and the scripted client never validated schemas so this only
        # appeared on the first call to a real endpoint.
        "order": {"type": "string", "enum": list(ORDERS),
                  "description": "which end of the data matters, because that end "
                                 "is what survives the row limit. 'highest' for a "
                                 "cost, a penalty or a volume. 'lowest' for days of "
                                 "cover or anything where small is urgent. Getting "
                                 "this wrong drops exactly the rows you meant to "
                                 "show. Default highest"},
    },
    ["key", "kind", "x", "y"],
)
def chart_finding(key: str, kind: str, x: str, y: str,
                  title: Optional[str] = None, series: Optional[str] = None,
                  limit: Optional[int] = None,
                  order: Optional[str] = None,
                  rows: Optional[str] = None) -> Result:
    board = registry.current_board()
    if board is None:
        return Result(None, Origin.MISSING, "shared board",
                      note="there is no board open, so there is no finding to draw")

    entries = getattr(board, "entries", {})
    if key not in entries:
        # Naming what is actually there beats a bare refusal: the model has
        # usually misremembered the key rather than failed to read anything.
        return Result(None, Origin.MISSING, "shared board",
                      note=f"nothing on the board under '{key}'. Read it first. "
                           f"What is there: {', '.join(sorted(entries)) or 'nothing yet'}")

    entry = entries[key]
    # Not `rows`: that is the name of the parameter naming a path INTO this,
    # and shadowing it made the data arrive where the path belonged.
    data = getattr(entry, "value", None)
    out = build(data, kind, x, y, title=title or "", series=series,
                limit=limit or DEFAULT_LIMIT, order=order or "highest",
                rows_path=rows)

    if not isinstance(out, Chart):
        note = out.reason
        if out.available:
            note += f". Available: {', '.join(out.available)}"
        return Result(None, Origin.MISSING, f"board:{key}", note=note)

    origin = getattr(entry, "origin", "modelled")
    source = getattr(entry, "source", key)
    spec = out.as_dict() | {"from_key": key, "origin": origin, "source": source,
                            "fetched_at": getattr(entry, "fetched_at", None)}

    # Collected on the board so the surface that is rendering this turn can
    # draw it. The agent's prose and the chart are one answer, not two.
    adder = getattr(board, "add_chart", None)
    if callable(adder):
        adder(spec)

    # Derived from the finding, and no better than it: a chart of modelled
    # rows is modelled, and the badge on screen has to say so.
    drawn = Origin.DERIVED if origin in ("live", "cached", "derived") else Origin.MODELLED
    return Result(
        spec, drawn, f"engine/charting.py over {source}",
        note="; ".join(filter(None, [
            out.note,
            f"drawn from {origin} data" if drawn is Origin.MODELLED else "",
        ])),
    )


def demo() -> None:
    from core.provenance import Origin as O
    from graph import Board

    board = Board()
    board.write("impact.get_material_stock", Result(
        [{"material": "M-4471", "plant": "KRW1", "days_left": 9.1, "unit": "TON"},
         {"material": "M-4472", "plant": "KRW1", "days_left": 21.4, "unit": "TON"},
         {"material": "M-4478", "plant": "SBY1", "days_left": 4.0, "unit": "TON"}],
        O.LIVE, "API_MATERIAL_STOCK_SRV"))
    board.write("demand.get_demand_signal", Result(None, O.MISSING, "SAP IBP"))
    board.write("inventory.get_safety_stock_policy", Result(
        [{"material": "M-4471", "reorder_point": 608.5, "unit": "TON"}],
        O.MODELLED, "fixture:MaterialStock"))

    # Outside a handling there is nothing to draw, and it says so rather than
    # drawing whatever it was handed.
    assert chart_finding("x", "bar", "a", "b").origin is O.MISSING

    with registry.bind_board(board):
        r = chart_finding("impact.get_material_stock", "bar", "material",
                          "days_left", title="Cover in days")
        assert r.origin is O.DERIVED and r.trusted, r.brief()
        spec = r.value
        assert spec["from_key"] == "impact.get_material_stock"
        # days_left names its own unit, so the axis is days rather than the
        # TON the rows are measured in. That is what lets one chart span
        # materials that are not measured the same way.
        assert spec["origin"] == "live" and spec["unit"] == "days", spec["unit"]
        assert [p["x"] for p in spec["points"]] == ["M-4472", "M-4471", "M-4478"]
        assert board.charts and board.charts[-1] is spec, "the chart must reach the turn"
        print(f"  drew {len(spec['points'])} bars from a live finding, "
              f"origin {spec['origin']} ✓")

        # The refusal that matters most: a key nobody read. The model may not
        # chart something it remembers, only something on the board, and the
        # refusal names what is actually there.
        miss = chart_finding("impact.get_open_purchase_orders", "bar", "a", "b")
        assert miss.origin is O.MISSING, miss.brief()
        assert "Read it first" in miss.note, miss.note
        assert "impact.get_material_stock" in miss.note, miss.note
        print(f"  unread key refused, and the note lists what is on the board ✓")

        # A chart of modelled rows is modelled. Drawing it in the same ink as
        # live data is the quiet lie this check exists to prevent.
        soft = chart_finding("inventory.get_safety_stock_policy", "bar",
                             "material", "reorder_point")
        assert soft.origin is O.MODELLED and not soft.trusted, soft.brief()
        assert soft.value["origin"] == "modelled"
        assert "modelled" in soft.note, soft.note
        print(f"  a chart of modelled rows stays untrusted ✓")

        # A finding that holds no rows cannot become a picture.
        assert chart_finding("demand.get_demand_signal", "bar", "a",
                             "b").origin is O.MISSING

        # Column mistakes come back with the columns, so the next attempt is
        # informed rather than another guess.
        wrong = chart_finding("impact.get_material_stock", "bar", "material", "plant")
        assert wrong.origin is O.MISSING and "days_left" in wrong.note, wrong.note

        before = len(board.charts)
        chart_finding("impact.get_material_stock", "pie", "material", "days_left")
        assert len(board.charts) == before, "a refused chart must not reach the turn"

    # A finding that keeps its rows inside an object, two levels down, with
    # two candidates. This is propose_allocation's actual shape, and it is the
    # most chart-worthy answer in the system.
    nested = Board()
    nested.write("impact.propose_allocation", Result({
        "feasible": False, "saving_idr": 67_000_000,
        "proposed": {"rule": "penalty first", "orders": [
            {"sales_order": "SO-1", "customer": "A", "penalty_idr": 98_000_000},
            {"sales_order": "SO-2", "customer": "B", "penalty_idr": 44_500_000}]},
        "by_date": {"rule": "due date", "orders": [
            {"sales_order": "SO-1", "customer": "A", "penalty_idr": 120_000_000}]},
    }, O.DERIVED, "engine/allocate.py"))

    with registry.bind_board(nested):
        amb = chart_finding("impact.propose_allocation", "bar", "customer", "penalty_idr")
        assert amb.origin is O.MISSING, amb.brief()
        assert "proposed.orders" in amb.note and "by_date.orders" in amb.note, amb.note
        print("  two nested row lists refused, both paths named ✓")

        drawn = chart_finding("impact.propose_allocation", "bar", "sales_order",
                              "penalty_idr", order="highest", rows="proposed.orders")
        assert drawn.origin is O.DERIVED, drawn.brief()
        # penalty_idr names its own unit, so no row unit is needed at all.
        assert drawn.value["unit"] == "Rp", drawn.value["unit"]
        assert [p["y"] for p in drawn.value["points"]] == [98_000_000, 44_500_000]
        print(f"  charted proposed.orders in {drawn.value['unit']}, "
              f"largest first ✓")

        # The wrong plan must not be reachable by accident.
        other = chart_finding("impact.propose_allocation", "bar", "sales_order",
                              "penalty_idr", rows="by_date.orders")
        assert other.value["points"][0]["y"] == 120_000_000, other.value
        assert chart_finding("impact.propose_allocation", "bar", "a", "b",
                             rows="nope.orders").origin is O.MISSING

    print("analyst ok")


if __name__ == "__main__":
    demo()
