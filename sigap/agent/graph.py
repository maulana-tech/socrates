"""The agent team. The lead calls specialists; each runs its own tool loop.

The pattern: specialists are exposed as tools belonging to the lead. The lead
decides who to call based on the last finding, there is no fixed sequence.
Each specialist runs its own tool-use loop to completion, then hands back a
summary along with the origin labels of the data behind it.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agents.definitions import ALL, SPECIALISTS, SUPERVISOR, Agent
import tools  # noqa: F401  (registers every tool; see tools/__init__.py)
from core import registry
from core.config import CFG
from core.provenance import Result

# Reference rates for the cost cap. Bedrock has its own pricing, replace these
# from aws.amazon.com/bedrock/pricing before going to production.
INPUT_IDR_PER_MILLION = 82_000
OUTPUT_IDR_PER_MILLION = 410_000
MAX_SPECIALIST_ROUNDS = 8
MAX_LEAD_ROUNDS = 14

#: Rounds and rupiah are not the only ways a handling can run away. One slow
#: specialist inside the round budget still blocks the queue behind it, so the
#: whole handling carries a deadline as well.
#: How long one handling may take. Measured against SAP AI Core, a seven
#: specialist handling ran 75 steps and was still working at 600s, so the old
#: constant turned a working handling into a failed one. Configurable because
#: the right answer depends on the model endpoint's latency, and a demo wants
#: a shorter ceiling than an overnight run does.
MAX_SECONDS_PER_EVENT = int(os.environ.get("SIGAP_EVENT_SECONDS", "1800"))


class BudgetExhausted(RuntimeError):
    pass


class DeadlineExceeded(RuntimeError):
    pass


class ModelNotReady(RuntimeError):
    pass


@dataclass(frozen=True)
class Entry:
    """One finding, with where it came from, kept together.

    The board used to be three parallel dicts keyed by the same string, which
    meant a value could exist without its origin. Since the origin is the whole
    point, they travel as one record.
    """
    value: Any
    origin: str
    source: str
    at: str


@dataclass
class Board:
    """The shared blackboard. Every specialist reads and writes here."""
    entries: Dict[str, Entry] = field(default_factory=dict)
    #: Charts drawn from the entries above during this turn. A list rather
    #: than a dict because one answer may want two of them, and keying on the
    #: tool name would mean the second quietly replaced the first.
    charts: List[dict] = field(default_factory=list)

    def add_chart(self, spec: dict) -> None:
        self.charts.append(spec)

    def write(self, key: str, r: Result) -> None:
        # A second call to the same tool is a second piece of evidence, not a
        # correction of the first. Overwriting lost it, and a specialist that
        # read two materials and then drew a chart drew whichever call landed
        # last: in a real handling it charted the empty one and said so in its
        # own words, "the chart board was overwritten by the empty M-5512 call
        # landing last under the same key".
        #
        # The first call keeps the plain key, so everything that refers to
        # `agent.tool` still finds the first read, and later calls are
        # numbered. The board summary lists them, so the model can name one.
        if key in self.entries:
            n = 2
            while f"{key}#{n}" in self.entries:
                n += 1
            key = f"{key}#{n}"
        self.entries[key] = Entry(r.value, r.origin.value, r.source,
                                  r.fetched_at.isoformat(timespec="seconds"))

    # Read shapes the rest of the system already expects.
    @property
    def findings(self) -> Dict[str, Any]:
        return {k: e.value for k, e in self.entries.items()}

    @property
    def origin(self) -> Dict[str, str]:
        return {k: e.origin for k, e in self.entries.items()}

    @property
    def source(self) -> Dict[str, str]:
        return {k: e.source for k, e in self.entries.items()}

    def untrusted_keys(self) -> List[str]:
        return [k for k, e in self.entries.items()
                if e.origin not in ("live", "cached", "derived")]

    def compliance_cost(self) -> Optional[dict]:
        """What obeying the rules cost, if the calculator worked it out.

        Lifted off the board rather than passed around, because which
        specialist ran the simulation is the supervisor's choice at the time
        and not something the caller should have to know.
        """
        for e in self.entries.values():
            if isinstance(e.value, dict) and e.value.get("compliance_cost"):
                return e.value["compliance_cost"]
        return None

    def summary(self) -> str:
        lines = [f"- {k}: {e.origin} ({e.source})" for k, e in self.entries.items()]
        return "\n".join(lines) or "(the board is still empty)"


@dataclass
class Cost:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def idr(self) -> int:
        return round(self.input_tokens / 1e6 * INPUT_IDR_PER_MILLION
                     + self.output_tokens / 1e6 * OUTPUT_IDR_PER_MILLION)

    def add(self, usage) -> None:
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.input_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0


def client():
    """Whatever can serve Claude on this machine.

    Bedrock first when a region is configured, because that is the path the
    deployment plan is written around. SAP AI Core otherwise, which on the
    hackathon tenant is a RUNNING Claude deployment that cost nothing extra
    and was unreachable until there was a client for it.
    """
    if not CFG.model_ready:
        raise ModelNotReady(
            "No model access. Set AWS_REGION for Bedrock, or put an AI Core "
            "service key at sigap/agent/.secrets/ai-core.json. Without one the "
            "team refuses to reason rather than guessing."
        )

    if not CFG.aws_region:
        from clients import ai_core
        return ai_core.client()

    # imported here so a dev machine without the SDK can still run the rest
    try:
        from anthropic import AnthropicBedrock
        return AnthropicBedrock(aws_region=CFG.aws_region)
    except Exception:
        from anthropic import AnthropicBedrockMantle
        return AnthropicBedrockMantle(aws_region=CFG.aws_region)


# --------------------------------------------------------------------------- #
def _build_user_content(prompt_text: str,
                        attachments: Optional[List[dict]] = None) -> Any:
    """Build Anthropic message content from prompt text and optional file/image attachments."""
    if not attachments:
        return prompt_text

    blocks: List[dict] = []
    text_parts: List[str] = []
    allowed_images = {"image/jpeg", "image/png", "image/gif", "image/webp"}

    for att in attachments:
        if not isinstance(att, dict):
            continue
        name = str(att.get("name") or "attachment")
        mime = str(att.get("mime_type") or "").lower()
        b64 = att.get("data")
        txt = att.get("text_content")

        if mime in allowed_images and isinstance(b64, str) and b64:
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": b64,
                },
            })
        elif mime == "application/pdf" and isinstance(b64, str) and b64:
            blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            })
        elif isinstance(txt, str) and txt:
            text_parts.append(
                f"Attached file '{name}' ({mime or 'text'}):\n```\n{txt[:30000]}\n```"
            )
        else:
            text_parts.append(f"[Attached file: {name} ({mime or 'binary'})]")

    combined_text = ("\n\n".join(text_parts) + "\n\n" + prompt_text) if text_parts else prompt_text
    if blocks:
        return [*blocks, {"type": "text", "text": combined_text}]
    return combined_text


def _tool_loop(cl, agent: Agent, task: str, board: Board,
               cost: Cost, report: Callable[[str, dict], None],
               deadline: Optional[float] = None,
               history: Optional[List[dict]] = None,
               attachments: Optional[List[dict]] = None) -> str:
    """One specialist works to completion. Returns the summary it wrote.

    `history` is earlier turns of the same conversation, already trimmed by the
    caller. Without it a follow-up question like "and the other plant?" has
    nothing to refer to, and the transcript on screen would be a record of a
    conversation the agent was never actually having.
    """
    tools = (
        (_specialist_tools() + registry.schemas_for_model(agent.code))
        if agent.code == "supervisor"
        else registry.schemas_for_model(agent.code)
    )
    prompt_text = (
        f"{task}\n\n"
        f"What is on the shared board right now:\n{board.summary()}\n\n"
        "Use your tools as needed, then write up what you found. If data you "
        "need is unavailable, say what is missing, do not guess.\n\n"
        "When your answer is a comparison across more than about four rows, or "
        "a movement over time, draw it with chart_finding and write one "
        "sentence reading it. A chart plus a sentence is read in seconds; the "
        "same figures as a paragraph are read by nobody. Pass the board key of "
        "something you have already read, never the numbers themselves."
    )
    messages: List[dict] = [*(history or []), {
        "role": "user",
        "content": _build_user_content(prompt_text, attachments),
    }]

    for _ in range(MAX_SPECIALIST_ROUNDS):
        if cost.idr > CFG.cost_cap_per_event_idr:
            raise BudgetExhausted(f"over Rp {CFG.cost_cap_per_event_idr:,} per event")
        if deadline and time.monotonic() > deadline:
            raise DeadlineExceeded(
                f"{agent.title} still working after {MAX_SECONDS_PER_EVENT}s")

        req = {
            "model": CFG.model,
            "max_tokens": 16000 if agent.code == "supervisor" else 8000,
            "system": agent.instructions,
            "tools": tools,
            "messages": messages,
        }
        if "haiku" not in CFG.model.lower():
            req["thinking"] = {"type": "adaptive"}
            req["output_config"] = {"effort": agent.effort}
        r = cl.messages.create(**req)
        cost.add(r.usage)
        messages.append({"role": "assistant", "content": r.content})

        thinking_text = "\n\n".join(
            getattr(b, "thinking", "")
            for b in r.content
            if getattr(b, "type", None) == "thinking" and getattr(b, "thinking", "")
        ).strip()
        note_text = "\n\n".join(
            getattr(b, "text", "")
            for b in r.content
            if getattr(b, "type", None) == "text" and getattr(b, "text", "")
        ).strip()

        if r.stop_reason != "tool_use":
            text = "".join(b.text for b in r.content if b.type == "text")
            if agent.code == "supervisor":
                report("summary", {"agent": "supervisor", "name": "Arya",
                                   "summary": "Formulating final mitigation recommendation",
                                   "full_summary": text,
                                   "thinking": thinking_text})
            else:
                report("specialist_done", {"agent": agent.code, "name": agent.nickname,
                                           "summary": text[:400],
                                           "full_summary": text,
                                           "thinking": thinking_text})
            return text

        # every tool_result MUST go back in ONE user message
        results: List[dict] = []
        for b in r.content:
            if b.type != "tool_use":
                continue
            if b.name.startswith("ask_") and b.name[len("ask_"):] in ALL:
                code = b.name[len("ask_"):]
                specialist = ALL[code]
                task_text = b.input.get("task", "")
                report("specialist_start", {"agent": code, "name": specialist.nickname,
                                            "task": task_text,
                                            "thinking": thinking_text or note_text})
                summary = _tool_loop(cl, specialist, task_text, board, cost, report, deadline)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": summary})
                continue

            try:
                res = registry.run(b.name, dict(b.input))
                board.write(f"{agent.code}.{b.name}", res)
                body = json.dumps({"value": res.value, **res.brief()},
                                  ensure_ascii=False, default=str)
                report("tool", {
                    "agent": agent.code,
                    "name": b.name,
                    "arguments": b.input,
                    "result": res.value,
                    "origin": res.origin.value,
                    "source": res.source,
                    # The model already gets this in the tool_result. Without
                    # it here the interface shows a tool that did nothing and
                    # no reason, which is the same unexplained blank the
                    # provenance labels exist to prevent.
                    "note": res.note or None,
                    "thinking": thinking_text or note_text,
                })
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": body})
            except Exception as e:                                   # noqa: BLE001
                err_msg = f"{type(e).__name__}: {e}"
                report("tool", {
                    "agent": agent.code,
                    "name": b.name,
                    "arguments": b.input,
                    "error": err_msg,
                    "thinking": thinking_text or note_text,
                })
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": err_msg, "is_error": True})
        messages.append({"role": "user", "content": results})

    return f"[{agent.title} stopped: exceeded {MAX_SPECIALIST_ROUNDS} tool rounds]"


def _specialist_tools() -> List[dict]:
    """Each specialist appears as one tool belonging to the lead."""
    return [{
        "name": f"ask_{a.code}",
        "description": (f"{a.nickname} ({a.title}), {a.brief}"
                        + (" HAS VETO." if a.veto else "")),
        "input_schema": {
            "type": "object",
            "properties": {"task": {
                "type": "string",
                "description": "the specific question for this specialist, with the context they need",
            }},
            "required": ["task"],
            "additionalProperties": False,
        },
        "strict": True,
    } for a in SPECIALISTS]


def run(event: dict, report: Callable[[str, dict], None]) -> dict:
    """Handle one event. `report` is called on every piece of progress."""
    return _handle_event(event, report, Board())


def _handle_event(event: dict, report: Callable[[str, dict], None], board: Board,
                  cl=None) -> dict:
    # `cl` is injectable so the cost-on-failure path can be checked without a
    # model endpoint. A self-check that reaches a paid endpoint is a check
    # nobody can run on a laptop, and it was briefly one.
    cl = cl or client()
    cost = Cost()
    # The board is the evidence in force for this handling, and it is bound
    # here, where it is actually used, rather than one level up in run(). A
    # tool asks the board how trustworthy the ground under it is without being
    # handed it through every call: execution refuses to act on its own
    # authority when anything under the decision is untrusted, and the chart
    # tool refuses to draw a finding nobody read. Bound in run() alone, any
    # other entry into a handling got neither.
    try:
        with registry.bind_board(board):
            return _handle(event, report, board, cl, cost)
    except Exception as e:
        # Tokens were spent whether or not the handling finished. Closing a
        # failed run without the cost recorded Rp 0 against a handling that
        # had made dozens of model calls, which also hid it from the cap.
        e.cost_idr = cost.idr                                    # type: ignore[attr-defined]
        raise


def _handle(event: dict, report: Callable[[str, dict], None], board: Board,
            cl, cost: "Cost") -> dict:
    called: List[str] = []
    deadline = time.monotonic() + MAX_SECONDS_PER_EVENT

    lead_tools = _specialist_tools() + registry.schemas_for_model("supervisor")
    messages: List[dict] = [{
        "role": "user",
        "content": (
            f"Incoming event:\n{json.dumps(event, ensure_ascii=False, indent=2)}\n\n"
            "Handle it. Call only the specialists that are relevant, one at a time, "
            "based on what the previous one found. Stop as soon as your evidence is "
            "enough to decide."
        ),
    }]

    for _ in range(MAX_LEAD_ROUNDS):
        if cost.idr > CFG.cost_cap_per_event_idr:
            raise BudgetExhausted(f"over Rp {CFG.cost_cap_per_event_idr:,}")
        if time.monotonic() > deadline:
            raise DeadlineExceeded(f"handling ran past {MAX_SECONDS_PER_EVENT}s")

        lead_req = {
            "model": CFG.model,
            "max_tokens": 16000,
            "system": SUPERVISOR.instructions,
            "tools": lead_tools,
            "messages": messages,
        }
        if "haiku" not in CFG.model.lower():
            lead_req["thinking"] = {"type": "adaptive"}
            lead_req["output_config"] = {"effort": SUPERVISOR.effort}
        r = cl.messages.create(**lead_req)
        cost.add(r.usage)
        messages.append({"role": "assistant", "content": r.content})

        if r.stop_reason != "tool_use":
            text = "".join(b.text for b in r.content if b.type == "text")
            return {
                "status": "done",
                "recommendation": text,
                "agents_called": called,
                "cost_idr": cost.idr,
                "untrusted_on_board": board.untrusted_keys(),
                # The veto is the thing this product is for, so what it cost
                # travels with the decision rather than staying in a tool result
                # nobody reads.
                "compliance_cost": board.compliance_cost(),
                # Anything the specialists drew. A real handling called
                # chart_finding three times and every chart was dropped here,
                # so the feature worked in conversation and nowhere else.
                "charts": board.charts,
            }

        results: List[dict] = []
        for b in r.content:
            if b.type != "tool_use":
                continue
            if b.name.startswith("ask_"):
                code = b.name[len("ask_"):]
                specialist = ALL[code]
                called.append(code)
                report("specialist_start", {"agent": code, "name": specialist.nickname,
                                            "task": b.input.get("task", "")})
                summary = _tool_loop(cl, specialist, b.input["task"], board, cost,
                                     report, deadline)
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": summary})
            else:
                try:
                    res = registry.run(b.name, dict(b.input))
                    board.write(f"supervisor.{b.name}", res)
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": json.dumps({"value": res.value, **res.brief()},
                                                          ensure_ascii=False, default=str)})
                except Exception as e:                               # noqa: BLE001
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": f"{type(e).__name__}: {e}", "is_error": True})
        messages.append({"role": "user", "content": results})

    return {"status": "stopped", "reason": f"exceeded {MAX_LEAD_ROUNDS} lead rounds",
            "agents_called": called, "cost_idr": cost.idr}


def ask_specialist(code: str, question: str,
                   report: Optional[Callable[[str, dict], None]] = None,
                   history: Optional[List[dict]] = None,
                   attachments: Optional[List[dict]] = None) -> dict:
    """Ask one specialist directly, outside of disruption handling.

    This is what the per-agent conversation page uses. Same specialist, same
    tools, the only difference is that no lead is deciding the turn order.
    """
    if code not in ALL:
        raise KeyError(code)
    agent = ALL[code]
    board, cost = Board(), Cost()
    trail: List[dict] = []

    def capture(kind: str, d: dict) -> None:
        trail.append({"kind": kind, **d})
        if report:
            report(kind, d)

    start_time = time.monotonic()
    cl = client()
    # The board has to be in force here too, exactly as in run(). It was not,
    # so every board-reading tool was blind in a direct conversation: a chart
    # the agent asked for came back refused and the answer arrived as prose
    # with nothing under it, which is the case this path exists to serve.
    #
    # This does not widen what an agent may do. Autonomy is gated on the run,
    # not the board, and raise_action refuses outright when no run is open, so
    # a conversation still cannot raise an action whatever is on the board.
    with registry.bind_board(board):
        answer = _tool_loop(cl, agent, question, board, cost, capture,
                            history=history, attachments=attachments)
    duration_s = round(time.monotonic() - start_time, 2)
    return {
        "agent": code,
        "name": agent.nickname,
        "role": agent.title,
        "answer": answer,
        "tools_used": [t["name"] for t in trail if t["kind"] == "tool"],
        # The prose and the charts are one answer. They travel together so the
        # surface rendering this turn does not have to go looking.
        "charts": board.charts,
        "board": {k: {"origin": board.origin[k], "source": board.source[k]}
                  for k in board.findings},
        "untrusted": board.untrusted_keys(),
        "cost_idr": cost.idr,
        "thinking_time": duration_s,
        "trail": trail,
        "tokens": {
            "input": cost.input_tokens,
            "output": cost.output_tokens,
            "total": cost.input_tokens + cost.output_tokens,
        },
    }


# --------------------------------------------------------------------------- #
# A scripted stand-in for Bedrock, so the loop above can be exercised without
# credentials. It is not a mock of the model's judgement: it plays a fixed
# sequence of tool calls and replies, which is enough to prove that the routing,
# the tool_result envelope, the board and the cost accounting all hold together.
# The real thing is still the real thing. This only means the first run against
# Bedrock is not also the first run of this file.
class _Reply:
    def __init__(self, blocks, stop_reason):
        self.content = blocks
        self.stop_reason = stop_reason
        self.usage = _Usage()


class _Usage:
    input_tokens = 1200
    cache_read_input_tokens = 0
    output_tokens = 300


class _Text:
    type = "text"

    def __init__(self, text): self.text = text


class _ToolUse:
    type = "tool_use"
    _n = 0

    def __init__(self, name, arguments):
        _ToolUse._n += 1
        self.id = f"toolu_{_ToolUse._n:03d}"
        self.name = name
        self.input = arguments


class ScriptedClient:
    """Replays a queue of replies, one per messages.create call."""

    def __init__(self, script):
        self._script = list(script)
        self.calls: List[dict] = []
        self.messages = self

    def create(self, **kwargs):
        # The envelope matters as much as the content: a malformed tool_result
        # is the failure that only shows up against the real API.
        for m in kwargs["messages"]:
            if m["role"] != "user" or not isinstance(m["content"], list):
                continue
            for block in m["content"]:
                if block.get("type") == "tool_result":
                    assert "tool_use_id" in block, "tool_result without tool_use_id"
                    assert isinstance(block["content"], str), "tool_result content must be text"
        self.calls.append({"system": kwargs["system"][:40],
                           "tools": [t["name"] for t in kwargs["tools"]]})
        if not self._script:
            return _Reply([_Text("nothing further")], "end_turn")
        return self._script.pop(0)


def demo() -> None:
    """Drive one event through the whole team with the scripted client."""
    from core import store

    seen: List[str] = []

    def report(kind, d):
        seen.append(f"{kind}:{d.get('agent', '')}")

    # Arya calls Elsa, then Kira, then writes up. Elsa reads stock, Kira rules.
    script = [
        _Reply([_ToolUse("ask_impact", {"task": "What does the Ningbo closure hit?"})], "tool_use"),
        _Reply([_ToolUse("get_material_stock", {"material": "M-4471", "plant": "KRW1"})], "tool_use"),
        _Reply([_Text("M-4471 at KRW1 has 84 t against 9.2 t/day.")], "end_turn"),
        _Reply([_ToolUse("ask_compliance", {"task": "Rule on the replacement options."})], "tool_use"),
        _Reply([_ToolUse("check_local_constraints", {"option_id": "E"})], "tool_use"),
        _Reply([_Text("Option E is blocked: TKDN falls to 34.8%.")], "end_turn"),
        _Reply([_Text("Recommend B+C. E is cheaper and is not available to us.")], "end_turn"),
    ]
    cl = ScriptedClient(script)

    event = {"id": "evt_demo", "kind": "port_closure",
             "title": "Typhoon closes the Port of Ningbo", "trigger": "maritime advisory"}

    board, cost, called = Board(), Cost(), []
    messages: List[dict] = [{"role": "user", "content": json.dumps(event)}]
    lead_tools = _specialist_tools() + registry.schemas_for_model("supervisor")

    # Mirror run() without its client() call, which needs a real region.
    for _ in range(MAX_LEAD_ROUNDS):
        r = cl.messages.create(model=CFG.model, max_tokens=16000,
                               system=SUPERVISOR.instructions, tools=lead_tools,
                               messages=messages)
        cost.add(r.usage)
        messages.append({"role": "assistant", "content": r.content})
        if r.stop_reason != "tool_use":
            recommendation = "".join(b.text for b in r.content if b.type == "text")
            break
        results = []
        for b in r.content:
            if b.type != "tool_use":
                continue
            code = b.name[len("ask_"):]
            called.append(code)
            summary = _tool_loop(cl, ALL[code], b.input["task"], board, cost, report)
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": summary})
        messages.append({"role": "user", "content": results})

    assert called == ["impact", "compliance"], called
    assert "Recommend B+C" in recommendation, recommendation
    assert "impact.get_material_stock" in board.findings, list(board.findings)
    assert "compliance.check_local_constraints" in board.findings, list(board.findings)

    # The board must remember where each finding came from, because the
    # calculator's refusal downstream depends on exactly this. The stock here
    # is a fixture and so is modelled; Kira now rules from references/, so her
    # finding is derived and the board must treat the two differently.
    assert board.origin["impact.get_material_stock"] == "modelled"
    assert "impact.get_material_stock" in board.untrusted_keys()

    # Asserted as a property, not a value: whichever origin Kira's ruling
    # carries, the board's trust list has to agree with it. Pinning the string
    # is what made this check fail the day the rule pack was written, which is
    # the day it should have passed.
    kira = board.origin["compliance.check_local_constraints"]
    assert (kira in ("live", "cached", "derived")) == (
        "compliance.check_local_constraints" not in board.untrusted_keys()), kira

    ruling = board.findings["compliance.check_local_constraints"]
    assert ruling["allowed"] is False and "TKDN" in ruling["reason"], ruling

    assert cost.idr > 0, "token accounting never ran"

    # Value and origin are one record, so a finding cannot exist without saying
    # where it came from.
    for key, entry in board.entries.items():
        assert entry.origin and entry.source and entry.at, (key, entry)
    assert set(board.findings) == set(board.origin) == set(board.entries)
    assert seen.count("specialist_done:impact") == 1, seen

    _check_failure_paths()

    print(f"graph ok, {len(called)} specialists called: {' then '.join(called)}")
    print(f"  board     {len(board.findings)} findings, "
          f"{len(board.untrusted_keys())} not yet trustworthy")
    for k in sorted(board.untrusted_keys()):
        print(f"            {k} is {board.origin[k]} from {board.source[k]}")
    print(f"  cost      Rp {cost.idr:,} across {len(cl.calls)} model calls")
    print(f"  answer    {recommendation}")

    # A chart drawn during a turn has to reach the turn, or the prose and the
    # picture arrive as two unrelated things and the surface has to go hunting.
    from core import registry as _reg
    from core.provenance import Origin
    from tools.analyst import chart_finding

    drawn = Board()
    drawn.write("impact.get_material_stock", Result(
        [{"material": "M-4471", "days_left": 9.1, "unit": "TON"},
         {"material": "M-4472", "days_left": 21.4, "unit": "TON"}],
        Origin.LIVE, "API_MATERIAL_STOCK_SRV"))
    with _reg.bind_board(drawn):
        chart_finding("impact.get_material_stock", "bar", "material", "days_left")
    assert len(drawn.charts) == 1, drawn.charts
    assert drawn.charts[0]["origin"] == "live", drawn.charts[0]
    # The key the surface reads is on the answer, not somewhere else.
    import inspect
    assert '"charts": board.charts' in inspect.getsource(ask_specialist)
    print(f"  charts    {len(drawn.charts)} drawn from the board and carried on the answer")

    # A second call to the same tool must not erase the first. A specialist
    # that read two materials and then charted "the" key charted whichever
    # call landed last, and in a real handling that was the empty one.
    twice = Board()
    for v, src in ((["M-4471"], "first"), ([], "second")):
        twice.write("sourcing.find_alternate_sources", Result(v, Origin.CACHED, src))
    assert list(twice.entries) == ["sourcing.find_alternate_sources",
                                   "sourcing.find_alternate_sources#2"], list(twice.entries)
    assert twice.findings["sourcing.find_alternate_sources"] == ["M-4471"]
    assert "#2" in twice.summary(), twice.summary()
    print("  board     a second call is kept as #2, the first is still there ✓")

    # And what was spent has to survive a failure, or a handling that burns
    # tokens and then times out is recorded as having cost nothing.
    # A chart drawn while handling a disruption has to reach the decision.
    # In a real run three were drawn and all three were dropped, so the
    # feature worked in conversation and nowhere else.
    shown = Board()
    handled = _handle_event(
        {"id": "evt_c", "kind": "port_closure", "title": "Typhoon closes Ningbo",
         "trigger": "advisory"},
        lambda k, d: None, shown, cl=ScriptedClient([
            _Reply([_ToolUse("ask_impact", {"task": "what is hit"})], "tool_use"),
            _Reply([_ToolUse("get_material_stock",
                             {"material": "M-4471", "plant": "KRW1"})], "tool_use"),
            _Reply([_ToolUse("chart_finding", {
                "key": "impact.get_material_stock", "kind": "bar",
                "x": "Material", "y": "DailyConsumption"})], "tool_use"),
            _Reply([_Text("KRW1 is thin on M-4471.")], "end_turn"),
            _Reply([_Text("Recommend acting on M-4471.")], "end_turn"),
        ]))
    assert handled["status"] == "done", handled
    assert "charts" in handled, sorted(handled)
    assert len(handled["charts"]) == 1, handled["charts"]
    assert handled["charts"][0]["from_key"] == "impact.get_material_stock"
    print(f"  decision  carries {len(handled['charts'])} chart drawn during the "
          f"handling ✓")

    class Dies(ScriptedClient):
        """Answers once, charging for it, then falls over."""

        def create(self, **kwargs):
            if self.calls:
                raise RuntimeError("the endpoint went away")
            return super().create(**kwargs)

    spent = Board()
    try:
        _handle_event({"id": "evt_x", "kind": "port_closure",
                           "title": "Typhoon closes the Port of Ningbo",
                      "trigger": "t"}, lambda k, d: None, spent,
                      cl=Dies([_Reply(
                          [_ToolUse("detect_disruption", {"event_id": "evt_x"})],
                          "tool_use")]))
    except Exception as e:
        assert hasattr(e, "cost_idr"), f"{type(e).__name__} carries no cost"
        assert e.cost_idr > 0, "the failure recorded no cost for a call it made"
        print(f"  failure   carries the Rp {e.cost_idr:,} it had already spent ✓")
    else:
        raise AssertionError("the failing client did not fail the handling")


def _check_failure_paths() -> None:
    """The happy path is the easy half. These are the ways a handling ends badly."""
    from agents.definitions import PromptMissing

    # Every agent must be reachable, have a prompt, and expose a valid schema.
    for code, agent in ALL.items():
        assert agent.instructions, code               # raises PromptMissing if absent
        for spec in registry.schemas_for_model(code):
            assert spec["input_schema"]["additionalProperties"] is False, spec["name"]
            assert spec["strict"] is True, spec["name"]

    # An agent with no prompt raises rather than being sent an empty one.
    ghost = Agent("ghost", "Nemo", "Nobody", "does not exist")
    try:
        ghost.instructions
        raise AssertionError("a missing prompt must raise")
    except PromptMissing:
        pass

    # A tool that throws comes back as an error result, not a crashed handling.
    board, cost = Board(), Cost()
    seen: List[str] = []
    boom = ScriptedClient([
        _Reply([_ToolUse("check_local_constraints", {"option_id": "nope"})], "tool_use"),
        _Reply([_Text("that option does not exist")], "end_turn"),
    ])
    out = _tool_loop(boom, ALL["compliance"], "rule on ZZ", board,
                     cost, lambda k, d: seen.append(k))
    assert "does not exist" in out, out

    # A tool name the registry does not know is refused the same way.
    board2 = Board()
    unknown = ScriptedClient([
        _Reply([_ToolUse("no_such_tool", {})], "tool_use"),
        _Reply([_Text("recovered")], "end_turn"),
    ])
    assert _tool_loop(unknown, ALL["impact"], "go", board2, Cost(),
                      lambda k, d: None) == "recovered"
    assert not board2.entries, "a failed tool must not write to the board"

    # The spend cap stops a handling rather than letting it run on.
    spent = Cost(input_tokens=10**9, output_tokens=10**9)
    assert spent.idr > CFG.cost_cap_per_event_idr
    try:
        _tool_loop(ScriptedClient([]), ALL["impact"], "go", Board(), spent,
                   lambda k, d: None)
        raise AssertionError("the spend cap did not fire")
    except BudgetExhausted:
        pass

    # So does the deadline, independently of the spend.
    try:
        _tool_loop(ScriptedClient([]), ALL["impact"], "go", Board(), Cost(),
                   lambda k, d: None, deadline=time.monotonic() - 1)
        raise AssertionError("the deadline did not fire")
    except DeadlineExceeded:
        pass

    # Asking for an agent that does not exist is a KeyError, not a silent default.
    try:
        ask_specialist("nobody", "hello")
        raise AssertionError("an unknown agent must raise")
    except KeyError:
        pass


if __name__ == "__main__":
    # The assertions in demo() pin the orchestration loop, not the state of
    # anyone's .env. With a SAP key present the stock read comes back live and
    # the origin assertions flipped, reporting a failure that was only a key
    # being set.
    from core.config import fixtures_only

    fixtures_only(__file__, "SIGAP_GRAPH_CHECK")
    demo()
