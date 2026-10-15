"""Claude through SAP AI Core, as a stand-in for the Bedrock client.

The hackathon tenant has a RUNNING Claude deployment in AI Core's
foundation-models scenario, and nothing in this system could reach it: the
only model path was `AnthropicBedrock(aws_region=...)`, so `AWS_REGION` looked
like the last blocker to the team reasoning at all when the model had been
available the whole time, on SAP's own AI service, billed to the tenant the
competition issued.

This exposes the one call graph.py makes, `client().messages.create(**kwargs)`,
and returns something shaped like the Anthropic SDK's reply so the tool loop
does not have to know which path it is on.

Three things the AI Core passthrough does differently from Bedrock:

  - The deployment decides the model, so a `model` in the body is a 400:
    "the value for the 'model' parameter ... doesn't match model ID specified
    in the header". It is dropped here rather than at every call site.
  - Auth is OAuth2 client credentials against the tenant's XSUAA, not SigV4.
    The token lasts twelve hours and is cached; re-authenticating per call
    would add a round trip to every turn.
  - Replies are JSON, not SDK objects. The blocks below are dicts with
    attribute access, so `getattr(b, "type", None)` works for the loop AND
    `json.dumps` works when the loop appends them back into the history.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

TIMEOUT = int(os.environ.get("AICORE_TIMEOUT", "180"))

#: Where the service key lives when nothing says otherwise. Gitignored, 700.
DEFAULT_KEY_PATH = pathlib.Path(__file__).resolve().parent.parent / ".secrets" / "ai-core.json"

#: Re-auth this long before expiry rather than on it, so a long turn does not
#: lose its token halfway through.
TOKEN_MARGIN_SECONDS = 300

#: Deployments whose configuration name contains this are Claude.
CLAUDE_MARKER = "anthropic"


class AiCoreError(RuntimeError):
    pass


class MissingServiceKey(AiCoreError):
    pass


def key_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("AICORE_SERVICE_KEY") or DEFAULT_KEY_PATH)


def available() -> bool:
    try:
        return bool(service_key())
    except Exception:                                            # noqa: BLE001
        return False


_key: Optional[dict] = None


def service_key() -> dict:
    """The AI Core service key, from the path or from the environment.

    AICORE_SERVICE_KEY_JSON carries the whole document, for a deployment
    target where a file cannot be mounted. The file is preferred because a
    secret in an environment variable shows up in more places.
    """
    global _key
    if _key is not None:
        return _key

    inline = os.environ.get("AICORE_SERVICE_KEY_JSON", "").strip()
    if inline:
        _key = json.loads(inline)
    else:
        p = key_path()
        if not p.exists():
            raise MissingServiceKey(
                f"no AI Core service key at {p}. Download it from the BTP cockpit "
                f"(AI Core instance, Service Keys) or set AICORE_SERVICE_KEY_JSON."
            )
        _key = json.loads(p.read_text())

    for field in ("clientid", "clientsecret", "url"):
        if not _key.get(field):
            raise MissingServiceKey(f"the service key has no '{field}'")
    if not (_key.get("serviceurls") or {}).get("AI_API_URL"):
        raise MissingServiceKey("the service key has no serviceurls.AI_API_URL")
    return _key


def api_base() -> str:
    return service_key()["serviceurls"]["AI_API_URL"].rstrip("/")


_token: Dict[str, Any] = {"value": "", "expires": 0.0}


def token() -> str:
    if _token["value"] and time.time() < _token["expires"]:
        return _token["value"]

    k = service_key()
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": k["clientid"], "client_secret": k["clientsecret"],
    }).encode()
    req = urllib.request.Request(
        k["url"].rstrip("/") + "/oauth/token", data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise AiCoreError(f"could not get a token: HTTP {e.code} "
                          f"{e.read()[:200].decode(errors='replace')}") from e

    _token["value"] = out["access_token"]
    _token["expires"] = time.time() + max(
        60, int(out.get("expires_in", 3600)) - TOKEN_MARGIN_SECONDS)
    return _token["value"]


def _call(method: str, path: str, payload: Optional[dict] = None,
          resource_group: str = "default") -> dict:
    req = urllib.request.Request(
        api_base() + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={"Authorization": "Bearer " + token(),
                 "AI-Resource-Group": resource_group,
                 "Accept": "application/json",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise AiCoreError(f"HTTP {e.code} from {path}: "
                          f"{e.read()[:300].decode(errors='replace')}") from e


def deployments(resource_group: str = "default") -> List[dict]:
    return _call("GET", "/v2/lm/deployments", resource_group=resource_group).get(
        "resources", [])


_deployment: Optional[str] = None


def deployment_id() -> str:
    """Which deployment to invoke.

    Discovered rather than hardcoded, because a deployment id is tenant
    specific and an id written into the code is an id that rots. AICORE_DEPLOYMENT
    skips the lookup when it is known.
    """
    global _deployment
    if _deployment:
        return _deployment

    fixed = os.environ.get("AICORE_DEPLOYMENT", "").strip()
    if fixed:
        _deployment = fixed
        return _deployment

    running = [d for d in deployments()
               if d.get("status") == "RUNNING"
               and CLAUDE_MARKER in str(d.get("configurationName", "")).lower()]
    if not running:
        names = [d.get("configurationName") for d in deployments()]
        raise AiCoreError(
            "no RUNNING Claude deployment in AI Core. Deploy one from the "
            "foundation-models scenario in AI Launchpad, or set "
            f"AICORE_DEPLOYMENT. What is deployed: {names}")
    # Newest first, so a redeploy is picked up without touching configuration.
    running.sort(key=lambda d: str(d.get("createdAt") or ""), reverse=True)
    _deployment = str(running[0]["id"])
    return _deployment


class Block(dict):
    """A content block that answers to both `b.type` and `json.dumps`.

    The loop reads blocks with getattr and then appends the same objects back
    into the message history, so they have to be attribute-readable and
    serialisable at once. A dict subclass is both; an SDK-style object would
    have needed converting on the way out.
    """
    __getattr__ = dict.get


class Usage:
    def __init__(self, raw: dict):
        self.input_tokens = int(raw.get("input_tokens") or 0)
        self.output_tokens = int(raw.get("output_tokens") or 0)
        self.cache_read_input_tokens = int(raw.get("cache_read_input_tokens") or 0)


class Reply:
    def __init__(self, raw: dict):
        self.content = [Block(b) for b in raw.get("content", [])]
        self.stop_reason = raw.get("stop_reason")
        self.usage = Usage(raw.get("usage") or {})
        self.raw = raw


def _tools_for_passthrough(tools: Any) -> Any:
    """Tool definitions the passthrough will accept.

    `strict` turns on constrained decoding, and the passthrough compiles a
    grammar for it. With this system's tool set that grammar came to 526MB
    against a 300MB ceiling and every call failed:

        Compiled grammar size (526.7MB) exceeds maximum allowed size (300MB)

    So it is dropped, and **that costs something worth naming**: strict mode
    guarantees the arguments match the schema, and without it the model can
    hand in an argument the tool has no parameter for. graph._tool_loop already
    catches that and returns the error to the model as a tool_result, so the
    turn recovers rather than crashing, but the guarantee is gone on this path.
    Bedrock keeps it; only the passthrough loses it.
    """
    if not isinstance(tools, list):
        return tools
    return [{k: v for k, v in t.items() if k != "strict"}
            if isinstance(t, dict) else t for t in tools]


class _Messages:
    def create(self, **kwargs) -> Reply:
        payload = {k: v for k, v in kwargs.items() if k != "model" and v is not None}
        if "tools" in payload:
            payload["tools"] = _tools_for_passthrough(payload["tools"])
        # The deployment decides the model. Sending one is a 400 that reads
        # like a configuration error and is really a protocol difference.
        payload.setdefault("anthropic_version", "bedrock-2023-05-31")
        return Reply(_call(
            "POST", f"/v2/inference/deployments/{deployment_id()}/invoke", payload))


class Client:
    """Shaped like the Anthropic SDK client, as far as graph.py uses it."""

    def __init__(self) -> None:
        self.messages = _Messages()


def client() -> Client:
    return Client()


def demo() -> None:
    # Offline first: the translation is the part that breaks, and it should be
    # checkable on a machine with no key and no network.
    r = Reply({
        "content": [{"type": "text", "text": "looking"},
                    {"type": "tool_use", "id": "toolu_1",
                     "name": "get_material_stock",
                     "input": {"material": "M-4471", "plant": "KRW1"}}],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 592, "output_tokens": 91,
                  "cache_read_input_tokens": 0},
    })
    assert r.stop_reason == "tool_use"
    blocks = r.content
    assert getattr(blocks[0], "type", None) == "text" and blocks[0].text == "looking"
    assert blocks[1].type == "tool_use" and blocks[1].name == "get_material_stock"
    assert blocks[1].input["plant"] == "KRW1" and blocks[1].id == "toolu_1"
    # A block the loop asks for and the reply does not carry must come back
    # falsy rather than raising, because the loop filters on truthiness.
    assert not getattr(blocks[0], "thinking", "")
    # And the same objects have to survive being put back on the wire.
    assert json.loads(json.dumps({"role": "assistant", "content": blocks}))["content"][1]["name"] \
        == "get_material_stock"
    assert r.usage.input_tokens == 592 and r.usage.output_tokens == 91
    print("  reply translation ok: blocks read by attribute and serialise back")

    # `model` has to be dropped, which is the difference that produces a 400.
    sent = {}
    import clients.ai_core as me
    real = me._call
    me._call = lambda method, path, payload=None, **kw: sent.update(
        {"path": path, "payload": payload}) or {"content": [], "usage": {}}
    me._deployment = "dep123"
    try:
        me.Client().messages.create(model="anthropic.claude-opus-5", max_tokens=10,
                                    system="s", messages=[], tools=[])
    finally:
        me._call, me._deployment = real, None
    assert "model" not in sent["payload"], sent["payload"]
    assert sent["payload"]["anthropic_version"] == "bedrock-2023-05-31"
    assert sent["path"].endswith("/deployments/dep123/invoke"), sent["path"]
    print("  request translation ok: model dropped, deployment in the path")

    # strict has to go too, and this is the one that failed every single call
    # until it was found: the compiled grammar came to 526MB of a 300MB limit.
    assert _tools_for_passthrough(
        [{"name": "t", "input_schema": {}, "strict": True}]) == [
        {"name": "t", "input_schema": {}}]
    sent.clear()
    me._call = lambda method, path, payload=None, **kw: sent.update(
        {"payload": payload}) or {"content": [], "usage": {}}
    me._deployment = "dep123"
    try:
        me.Client().messages.create(max_tokens=10, messages=[], tools=[
            {"name": "a", "description": "d", "input_schema": {}, "strict": True}])
    finally:
        me._call, me._deployment = real, None
    assert "strict" not in sent["payload"]["tools"][0], sent["payload"]["tools"]
    print("  strict stripped: the grammar it compiles does not fit the limit")

    if not available():
        print("  no service key on this machine, so the live call was not made")
        print("ai_core ok")
        return

    # With a key, go and actually talk to it. This is the check that would
    # have caught the whole thing: the model was reachable all along.
    deps = [d for d in deployments() if d.get("status") == "RUNNING"]
    claude = [d for d in deps if CLAUDE_MARKER in str(d.get("configurationName", "")).lower()]
    print(f"  {len(deps)} running deployment(s), {len(claude)} of them Claude")
    assert claude, "no Claude deployment to talk to"

    out = Client().messages.create(
        max_tokens=200, system="You are terse.",
        messages=[{"role": "user", "content": "Reply with the single word READY."}])
    text = " ".join(b.text for b in out.content if b.type == "text")
    assert "READY" in text.upper(), text
    assert out.usage.input_tokens > 0 and out.usage.output_tokens > 0
    print(f"  live: {deployment_id()} replied '{text.strip()[:40]}', "
          f"{out.usage.input_tokens} in / {out.usage.output_tokens} out")
    print("ai_core ok")


if __name__ == "__main__":
    demo()
