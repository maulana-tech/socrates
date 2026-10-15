"""Otto's tools (Precedent).

Institutional memory: what was done last time something like this happened,
and how it turned out.

The memory is the runs and events tables. Every disruption the system has
finished handling is already written there with its decision, its cost and
who approved it, so there is nothing to build: there was only a tool that
never looked. A Bedrock Knowledge Base can sit in front of this later for
semantic recall, but it would be a second index over the same record, not a
second record.
"""
from __future__ import annotations

import pathlib
import re

from core.provenance import Origin, Result
from core.registry import register

LIMIT = 5

REFERENCES = pathlib.Path(__file__).resolve().parent.parent.parent / "references"
PRECEDENT_DOC = REFERENCES / "disruption-precedents.md"

#: A fenced block in the precedent document. One block is one precedent.
_BLOCK = re.compile(r"```\n(.*?)```", re.S)


def _library() -> list[dict]:
    """The documented real disruptions in references/disruption-precedents.md.

    Deliberately a separate store from the runs table. These happened to other
    companies, and writing them in as this installation's finished runs would
    manufacture an operational history, which is the exact laundering the
    provenance labels exist to prevent.
    """
    if not PRECEDENT_DOC.exists():
        return []
    out = []
    for body in _BLOCK.findall(PRECEDENT_DOC.read_text()):
        rec = {}
        for line in body.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                rec[k.strip()] = v.strip()
        # The parameters block at the foot of the document parses too. A
        # precedent is the one carrying an id and the lesson drawn from it.
        if rec.get("id") and rec.get("lesson"):
            out.append(rec)
    return out


def _terms(keywords: str) -> list[str]:
    """Words worth matching on. Two letters and under are noise, not signal."""
    return [t for t in re.split(r"[^\w-]+", keywords.lower()) if len(t) > 2]


@register("search_past_incidents", "precedent",
          "Find comparable past incidents and how their handling ended.",
          {"keywords": {"type": "string"}}, ["keywords"])
def search_past_incidents(keywords: str) -> Result:
    from core import store

    terms = _terms(keywords)
    if not terms:
        return Result([], Origin.MISSING, "runs + events tables",
                      note="no searchable word in the request")

    matches, total = store.past_incidents(terms, LIMIT)
    source = "runs + events tables"
    held = f"{total} handled incident{'' if total == 1 else 's'}"

    # Three outcomes, and only one of them is missing data. An empty list from
    # a search that genuinely ran is a determinate answer and says so; an empty
    # list because nothing has ever been handled is a hole. Collapsing the two
    # is how an agent ends up reading "no precedent" as "no risk".
    if total == 0:
        # Pointing at the fallback is the whole job here. An agent told only
        # "no precedent" reads it as "no risk", which is the wrong half of the
        # sentence: nothing comparable has happened *to us* yet.
        lib = len(_library())
        return Result([], Origin.MISSING, source,
                      note="nothing has been handled to completion yet, so there is "
                           "no memory to search. This is the first one"
                           + (f". {lib} documented industry precedents are available "
                              f"from search_industry_precedents" if lib else ""))
    if not matches:
        return Result([], Origin.DERIVED, source,
                      note=f"searched {held}, none mentions "
                           f"{', '.join(terms)}")
    return Result(matches, Origin.DERIVED, source,
                  note=f"{len(matches)} of {held} matched")


@register("search_industry_precedents", "precedent",
          "Find documented real-world disruptions comparable to this one, from the "
          "reference library rather than from this company's own history. Use it when "
          "search_past_incidents finds nothing, and to sanity-check an internal "
          "precedent against what the industry has already seen.",
          {"keywords": {"type": "string"}}, ["keywords"])
def search_industry_precedents(keywords: str) -> Result:
    lib = _library()
    source = "references/disruption-precedents.md"
    if not lib:
        return Result([], Origin.MISSING, source,
                      note="the precedent library is not written yet")

    terms = _terms(keywords)
    if not terms:
        return Result([], Origin.MISSING, source,
                      note="no searchable word in the request")

    scored = []
    for rec in lib:
        hay = " ".join(str(v) for v in rec.values()).lower()
        hits = sum(1 for t in terms if t in hay)
        if hits:
            scored.append(dict(rec, matched=hits))
    scored.sort(key=lambda r: (-r["matched"], r["date"]))

    # These are other companies' disruptions, published and dated. That makes
    # them usable as an analogue and useless as a price: a 1997 repair bill is
    # not a quotation, and the note has to say so where the model reads it.
    held = f"{len(lib)} documented precedent{'' if len(lib) == 1 else 's'}"
    if not scored:
        return Result([], Origin.DERIVED, source,
                      note=f"searched {held}, none mentions {', '.join(terms)}")
    return Result(scored[:LIMIT], Origin.DERIVED, source,
                  note=f"{len(scored)} of {held} matched. Other companies' incidents, "
                       f"not this installation's record. Use the mechanism and the "
                       f"lesson, not the figures, which are historical")


def demo() -> None:
    from core import store

    terms = _terms("Typhoon closes the Port of Ningbo, M-4471 at KRW1")
    assert "typhoon" in terms and "ningbo" in terms
    assert "of" not in terms and "at" not in terms, "short words are noise"

    before = search_past_incidents("typhoon Ningbo")
    total_before = store.past_incidents(terms)[1]
    if total_before == 0:
        assert before.origin is Origin.MISSING and not before.trusted, before.brief()
        # An empty internal memory must hand over, not just report emptiness.
        assert "search_industry_precedents" in before.note, before.note
        print("  no memory yet, and it points at the industry library instead")

    # Write one finished incident, then prove Otto can find it and that an
    # unrelated search still comes back determinate rather than missing.
    eid = store.record_event("port_closure", "Typhoon closes the Port of Ningbo",
                             "BMKG: test", {"port": "Ningbo"}, "precedent-check")
    rid = store.start_run(eid, "guided")
    store.close_run(rid, "done", decision={"status": "done", "chose": "B+C"}, cost_idr=1500)

    hit = search_past_incidents("typhoon Ningbo")
    assert hit.origin is Origin.DERIVED and hit.trusted, hit.brief()
    assert hit.value and hit.value[0]["title"].endswith("Ningbo"), hit.value
    assert hit.value[0]["decision"]["chose"] == "B+C", hit.value[0]
    assert hit.value[0]["matched"] == 2, hit.value[0]
    print(f"  found it: {hit.value[0]['title']} -> {hit.value[0]['decision']['chose']}")

    # The loop: an action that was sent, then what came of it. A precedent that
    # stops at "we decided X" is a diary; the useful part is "and it was late".
    from core import registry
    with registry.bind_run(rid):
        from tools.execution import raise_action
        act = raise_action("stock_transfer", True, material="M-4471",
                           from_plant="SBY1", to_plant="KRW1", qty=55, cost_idr=1_000_000)
    store.record_outcome(act.value["id"], "late",
                         {"note": "arrived 3 days after the promised date"})

    learned = search_past_incidents("typhoon Ningbo")
    acts = learned.value[0]["actions"]
    assert acts and acts[0]["outcome"] == "late", acts
    assert acts[0]["outcome_detail"]["note"].startswith("arrived 3 days"), acts[0]
    print(f"  and what came of it: {acts[0]['kind']} -> {acts[0]['outcome']}, "
          f"{acts[0]['outcome_detail']['note']}")

    # Both doors store the same shape. The HTTP endpoint hands in the sentence
    # a person typed; the tool hands in a dict. A reader looking for .note must
    # not have to know which one was used.
    from tools.execution import record_outcome as tool_record
    with registry.bind_run(rid):
        other = raise_action("notify", True, role="buyer", message="check")
    typed = tool_record(other.value["id"], "delivered", "landed on time")
    assert typed.value["outcome_detail"] == '{"note": "landed on time"}', \
        typed.value["outcome_detail"]
    print("  a typed sentence and a dict land in the same shape")

    # Reality is read once. A second reading does not quietly replace the first.
    again = store.record_outcome(act.value["id"], "delivered")
    assert again["repeated"] and again["outcome"] == "late", again
    print("  a second outcome does not overwrite the first")

    none = search_past_incidents("earthquake Surabaya")
    assert none.value == [] and none.origin is Origin.DERIVED, none.brief()
    assert none.trusted, "a search that ran and found nothing is an answer, not a gap"
    print(f"  unrelated search: empty but trusted, '{none.note}'")

    # Two memories, kept apart. The library is other companies' incidents and
    # must never surface as something this installation handled.
    lib = search_industry_precedents("port closure Ningbo typhoon")
    assert lib.origin is Origin.DERIVED and lib.value, lib.brief()
    assert lib.value[0]["id"] == "ningbo-meidong-2021", lib.value[0]
    assert all(m.get("lesson") and m.get("date") for m in lib.value), lib.value
    assert "not this installation's record" in lib.note, lib.note
    ours = {r["title"] for r in store.past_incidents(["ningbo", "port"], 50)[0]}
    assert not ours & {m["title"] for m in lib.value}, \
        "a library precedent surfaced as one of our own runs"
    print(f"  industry library: {len(_library())} documented, matched "
          f"'{lib.value[0]['id']}' on mechanism, kept out of our own runs ✓")

    gone = search_industry_precedents("earthquake Surabaya flood")
    assert gone.value == [] and gone.origin is Origin.DERIVED, gone.brief()

    # A documented precedent must not be able to authorise an autonomous act.
    from tools.execution import NOT_EVIDENCE
    assert "precedent.search_industry_precedents" in NOT_EVIDENCE

    print("precedent ok")


if __name__ == "__main__":
    # This check writes a specimen incident, so it must not touch a real DB.
    from core.config import fixtures_only

    fixtures_only(__file__, "SIGAP_PRECEDENT_CHECK")
    demo()
