# Architecture

> How SIGAP is put together and why each boundary is where it is. Written in
> English to match the code it describes; the build plan that drove this round
> of work is in `PLAN-OPERATE.md`.
>
> Updated 15 October 2026.

---

## The one idea

A language model decides **what to do**. Plain Python decides **what the
numbers are**. Every boundary below exists to keep those two apart, because a
rupiah figure that came out of a model cannot survive one sceptical question,
and a routing decision made by a formula cannot survive a disruption nobody
wrote a rule for.

Everything else follows from that, including the parts that look like
bureaucracy.

## Layers, and what may import what

```
                      next.js app  (app/, components/)
                             |  HTTP, read-only
                             v
  signals/ ------------>  api.py  <------------ mcp.py
  (clocks)              (routes)            (model tools)
                             |
                             v
                        graph.py            orchestration: who gets called
                             |
                             v
                         tools/             one module per agent, 36 tools
                             |                     returns Result, always
              +--------------+--------------+
              v                             v
          engine/                        clients/
   deterministic arithmetic     sap_s4, ai_core, bedrock
              |                             |
              +--------------+--------------+
                             v
                           core/
         provenance · registry · store · identity · config · rules
                             |
              +--------------+--------------+
              v                             v
        references/                    fixtures/
   written rules, as data          modelled data, labelled
```

**The rules of the arrows, and all three have been broken at least once:**

1. `engine/` may not import `tools/`, `clients/` or `core.store`. It takes
   plain rows and numbers and returns plain rows and numbers. Give it a
   fetcher and the arithmetic becomes untestable without a network.
2. `tools/` may not read `fixtures/` directly. It reads through
   `fetcher.pull()`, which is the one place that decides between live SAP, an
   upload and the fixture. Nine places were bypassing this and four agents ran
   on sample data with a live key set.
3. `core/` may not import `tools/` or `engine/`. `core/rules.py` exists
   because the rule reader used to live in `tools/compliance.py`, which meant
   the fetcher could not read the exchange rate without a circular import.

## The read path

One function answers "where does this number come from", and the order is a
judgement about authority, not convenience:

```python
# tools/fetcher.pull()
if is_mock_sap() and uploaded(entity):   return uploaded   # CACHED
if sap_s4.available():                   return live       # LIVE
if uploaded(entity):                     return uploaded   # CACHED
return fixture(entity)                                     # MODELLED
```

A public sandbox is a demonstration dataset carrying somebody else's
materials, so a company's own uploaded file outranks it. A genuine S/4HANA
tenant outranks the upload. That is why the test is on the base URL rather
than on a flag.

## Provenance

Every tool returns `Result(value, origin, source, fetched_at, note)`.
`Origin` is one of LIVE, CACHED, DERIVED, MODELLED, MISSING, and
`trusted` is derived from the origin alone, never set by hand.

**The rule with teeth:** if an input on a critical path is not trusted, the
calculator emits no rupiah figure at all. `engine/simulate.py` refuses and
says which input and where it came from. A MISSING result carries
`value=None`, because a failure that invents a value is worse than a failure.

## Determinism, and what the model is for

Everything with a number in it is Python:

| Engine | Answers |
|---|---|
| `engine/arrival.py` | when a shipment actually lands, and what moved it |
| `engine/planning.py` | what to hold, when to reorder, how much |
| `engine/simulate.py` | what each plan costs, and the penalty it leaves |
| `engine/allocate.py` | who gets served when supply is short |
| `engine/matching.py` | which plant can donate without breaking itself |
| `engine/forecast.py` | where demand is heading, with an interval |
| `engine/audit.py` | which records contradict each other |

The model chooses which of these to call, in what order, on what, and when the
evidence is enough to recommend. It never does the arithmetic. Kira's veto is
Python comparison operators, not a prompt, which is why it cannot be argued
out of a rejection.

## Dates: one answer, not three

`engine/arrival.py` is the only place that computes an effective arrival date.
Before it existed, Kira added the import permit, Milo added port dwell, and
`QualificationDays` sat on every option read by nobody, while the costing
engine planned on the raw date from master data. Three corrections computed,
three discarded, and a plan could be called safe while the goods landed
thirteen days after the stockout.

```
booked date
  + the longest PRE-SHIPMENT approval, in working days   (permit, qualification)
  + port dwell, in calendar days
= effective arrival
```

Pre-shipment approvals take the longest rather than the sum because they run
in parallel. The estimate carries its steps, so a buyer reads
`2026-09-26 LARTAS +10wd qualification +7wd dwell +5d = 2026-10-14` rather
than a number to take on trust. The date rides into the plan on
`Ruling.arrival_effective`, because the ruling is what already crosses that
boundary.

## The rules are documents

`references/` holds nine Markdown files with a `## Parameters` block each,
parsed by `core/rules.py` into 57 parameters. The TKDN floor, the LARTAS lead
time, 17 national holidays, the Priok dwell figure, the service level, the
exchange rate and the operating targets all live there.

This is deliberate and it is load-bearing. A constant in a Python file is a
rule nobody reviewed, and a document that merely agrees with a constant is
decoration until the day someone edits one of them. Change
`contract_floor_pct` in the Markdown and Kira's verdict changes. The pack is
globbed, not listed, because a document added and not registered is a rule
nobody enforces.

Every claim in those documents is marked **OFFICIAL**, **SECONDARY** or
**ASSUMED**, and where sources contradict each other the contradiction is
recorded rather than averaged away.

## Operating, not only responding

Four clocks, in `signals/watch.py`. Two react to something; two happen because
it is a new day or a new week, which is what operating a supply chain
consists of.

| Cadence | Every | Raises |
|---|---|---|
| BMKG weather and seismic | 5 min | a disruption event |
| Vega exposure scan | 7 days | the top 3 standing risks |
| Replenishment review | 24 h | one worklist of positions at their reorder point |
| Supplier review | 7 days | suppliers whose own dates stopped meaning anything |

Each raises an event through the same `POST /events` path a person would, so
every cadence lands in the same audit trail with the same autonomy limits. No
separate machinery.

## The loop closes

This is the difference between an agent and a tidy script.

```
policy  ->  proposal  ->  approval  ->  action  ->  outcome recorded
   ^                                                      |
   +------------------------------------------------------+
            store.delivery_observations()
```

`lead_time_stats()` takes observed deliveries alongside the dates on the
purchase orders. A delivery recorded as having run three weeks long becomes an
additional lead-time observation, which widens the spread, which raises the
safety stock and the reorder point behind that supplier. Nothing edits a
parameter: reality is observed and the next decision differs.

Measured, not asserted: the scorecard reports how many recorded outcomes are
actually feeding the planner, because an outcome nobody reads back is a diary
entry.

## Autonomy

Identity comes only from an HMAC token, never from a payload. The limit is
per role: `planner 0 · buyer 500m · procurement_lead and admin 10bn`, with a
Rp 50m ceiling on anything autonomous.

`autonomy_check()` refuses on three grounds, and the second is the one that
matters: value alone was once the whole test, and value is a number the model
hands in. So an action is also refused when the figures under it are not all
trusted, and when the only evidence on the board came from a tool that cannot
constitute evidence (`NOT_EVIDENCE`: both precedent searches). The reason is
stored on the action, not in the payload, because the payload feeds the
idempotency key.

## Two memories, never mixed

`search_past_incidents` reads this installation's own finished runs.
`search_industry_precedents` reads four documented real disruptions from
`references/disruption-precedents.md`. They are separate stores on purpose:
writing Aisin 1997 in as one of our runs would manufacture an operational
history, which is the exact laundering the provenance labels exist to prevent.

An empty internal memory hands over to the library rather than only reporting
emptiness, because an agent told "no precedent" reads it as "no risk".

## Storage

One SQLite file. `events` and `runs` carry the handling, `steps` the
reasoning, `actions` what was proposed and what became of it, `approvals` who
decided, `reservations` what one handling has promised so another cannot spend
it twice, `uploads` the company's own files. Migrations are an `ADDED_LATER`
list of columns applied on connect; there is no migration tool and at this
size there should not be.

## Self-checks

23 files carry a `demo()` behind `if __name__ == "__main__"`, run by
`python3 manage.py check`. No framework, no fixtures directory, no mocks.

Three rules learned the hard way:

- A check that writes must not touch the operator's database.
  `config.fixtures_only(__file__, "FLAG")` re-execs with `SAP_API_KEY=""` and
  a scratch DB. The key must be set **empty**, not removed, because
  `_load_env()` uses `setdefault` and `CFG` is frozen at import.
- A check must assert what has to be true, not what happens to be true today.
  Assertions pinned to `origin == "modelled"` broke the moment the data went
  live, and they were testing the fixture, not the system.
- A check that proves nothing is worse than no check. Where a real threshold
  finds nothing on a healthy book, the check passes an explicit override and
  exercises the path, rather than the threshold being tuned until a test goes
  green.

## Where to add things

| You want to | Put it |
|---|---|
| change a rule, a target, a rate | `references/*.md`, in a Parameters block |
| add arithmetic | `engine/`, with a `demo()` |
| give an agent a new ability | `tools/<agent>.py`, `@register`, then `agents/definitions.py` |
| read a new SAP entity | `fetcher.ENTITIES`, and a join in `JOINS` if it spans entities |
| add a cadence | `signals/watch.py`, one entry in `cadences()` |
| add a screen | a view in `tools/views.py`, then a page under `app/(app)/` |

## Two model paths

`graph.client()` returns Bedrock when `AWS_REGION` is set and SAP AI Core
otherwise. Only one was wired for most of this build, which made `AWS_REGION`
look like the last blocker while a RUNNING Claude deployment sat in AI Core on
the hackathon tenant. `clients/ai_core.py` translates the differences, all three
of which were found by a 400 from the live endpoint rather than from a document:
`model` in the body, `strict` on a tool, and an `enum` beside a nullable type.
`SAP-INTEGRATION.md` has the detail and what dropping `strict` costs.

The loop above does not know which path it is on, which is the point: the
client is shaped like the SDK's, blocks are dicts with attribute access so they
read with getattr and serialise back into the history, and the usage fields line
up with what `Cost` counts.

## Dependencies, and the five findings that stay

`npm audit` reported 13, one critical. After this round:

| | Before | After |
|---|---|---|
| critical | 1 | **0** |
| high | 12 | 5 |
| **in the production tree** | 11 | **0** |

What was done, and why the five remain:

- **next 16.3.4 to 16.4.1.** The critical finding was remote code execution in
  `next/og` ImageResponse. Re-pinned exactly rather than left on a caret,
  because this version of Next has breaking changes and a caret on a framework
  like that is how two machines get two builds.
- **shadcn removed from `dependencies`.** It is a component scaffolding CLI and
  it sat in the production dependency tree, where it pulled `fast-glob`,
  `micromatch` and `braces`. `app/globals.css` imported one stylesheet from it,
  so 629 lines of static CSS kept a whole CLI installed. That file is now
  vendored at `app/shadcn-tailwind.css` with its provenance and a refresh
  recipe in its header. `components.json` stays, so `npx shadcn@latest add`
  still works when a new component is wanted.
- **sharp, source-map-js, brace-expansion, @modelcontextprotocol/sdk** took
  ordinary patch bumps.

The five that remain are all one chain:

```
eslint-config-next@16.4.1 -> @next/eslint-plugin-next -> fast-glob -> micromatch -> braces@3.0.3
```

`braces` has a published denial-of-service advisory and **no patched release
exists**: there is no version above 3.0.3. npm's suggested fix is
`eslint-config-next@14.2.35`, which would mean linting a Next 16 app with a
Next 14 config. So the finding is accepted on three grounds: it is a
devDependency that never reaches a deployed artefact, `npm audit --omit=dev`
reports zero, and the only available "fix" is a two-major-version downgrade of
the linter. Revisit when `braces` ships a patch or `@next/eslint-plugin-next`
drops `fast-glob`.

## The honest ceiling

Two SAP write targets answer 403, because the hackathon BTP tenant carries AI
Core, Joule and a Cloud Foundry runtime and **no ERP**. So the operating loop
is complete through proposal, approval and recorded outcome, and the write to
SAP is proven against a mock rather than against a production ERP. This is
said out loud in the demo rather than left to be discovered.
