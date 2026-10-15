# SIGAP

**Supply Disruption Intelligence & Anticipation System**

An autonomous assistant for manufacturers that import most of their raw material. When
supply is disrupted, the system investigates the impact itself, assembles the ways out,
strikes the ones that break Indonesian regulation or the customer contract, works out
which is cheapest, and executes it into SAP once someone with the authority approves.

---

## Run it

```bash
cd sigap/agent
cp .env.example .env                      # then fill SIGAP_SECRET
python3 manage.py secret                  # its output goes in .env
python3 manage.py user budi@kpn.co.id "Budi" buyer secret123
python3 manage.py seed                    # optional demo data
python3 api.py                            # :8787

cd ../..
SIGAP_API=http://127.0.0.1:8787 npm run dev
open http://localhost:3000/dashboard
```

## Where to start

| You want to | Open |
|---|---|
| Set it up, key by key | `SETUP.md` |
| Understand the product | `PLAN.md` §1 and §3 |
| See how far along it is | `PLAN.md` §2, or `manage.py check` |
| Start writing code | `agent/README.md`, then `TECHNICAL.md` |
| Know what happens before Demo Day | `AWS-PLAN.md` |
| Meet the agents one by one | `AGENT-REFERENCE.md` |
| Find a number or the scenario | `DESIGN.md` §2 |
| Work out where data comes from | `DATA-SOURCES.md` |
| Know which AWS and SAP services we use | `BUILD-SPEC.md` |
| See what AWS and SAP themselves publish | `RESEARCH-AWS-SAP.md` |
| Understand how the code is put together | `ARCHITECTURE.md` |
| Know exactly how SAP is wired, and what refuses | `SAP-INTEGRATION.md` |
| Set up a machine, key by key, to hand to someone | `ENV.md` |
| See the operating build and what is left of it | `PLAN-OPERATE.md` |
| Deploy the agent service on its own | `AGENT-ONLY-EXTERNAL-DEPLOYMENT.md` |

## Contents

| File | What's in it |
|---|---|
| **`PLAN.md`** ⭐ | The plan, the status of each part, the order of work |
| **`SETUP.md`** | From a clone to a system that reasons. Every step ends with a test |
| **`AGENT-REFERENCE.md`** | All 12 agents: tools, parameters, limits. **Generated**, `manage.py docs` |
| **`AWS-PLAN.md`** | Getting onto Bedrock and AgentCore, in the order that survives contact with a loop that has never run |
| **`ARCHITECTURE.md`** | The layers and which may import which, the read path, where determinism ends and the model begins, the four cadences, the loop |
| **`SAP-INTEGRATION.md`** | Where SAP points, every service and join, what 403s, the rate limit, and what changes for a real tenant |
| **`ENV.md`** | Every variable, what it unlocks, and which keys were rotated |
| `PLAN-OPERATE.md` | The build that turned this from responding to operating |
| `DESIGN.md` | Scenario figures, local rules, the eval suite |
| `TECHNICAL.md` | Exact function names and parameters |
| `DATA-SOURCES.md` | What was verified about each data source |
| `BUILD-SPEC.md` | The wiring: every AWS and SAP service, and the three request paths |
| `RESEARCH-AWS-SAP.md` | What AWS and SAP publish about building this, read from their own pages |
| `agent/` | The code, see `agent/README.md` |

## Things to remember

**PLAN.md is the reference.** Where documents disagree, PLAN.md is right.

**AGENT-REFERENCE.md is generated, never edited.** It is derived from the live tool
registry, so it cannot drift from the code the way a hand-written copy does:

```bash
cd agent && PYTHONPATH=. python3 manage.py docs
```

**Numbers always come from DESIGN.md §2**, and the machine verifies them:

```bash
cd agent && PYTHONPATH=. python3 engine/simulate.py
```

If a figure in a document cannot be reproduced by that command, **the document is wrong.**

**What is blocking, right now.** Ask the machine rather than this paragraph, which
has been wrong before:

```bash
cd agent && PYTHONPATH=. python3 manage.py check
```

It prints the agent, tool and prompt counts live and names the keys that are not
set. A count written here instead goes stale the first time somebody adds a tool,
and this file claimed 31 for a while after there were more.

As of 15 October 2026 the shape of it is: `references/` is written, nine documents
and 57 parameters, and it drives the rulings rather than decorating them. The SAP
key is set but its **quota is exhausted**, so every read falls back to labelled
modelled data with the reason attached, see `SAP-INTEGRATION.md`. `AWS_REGION` is
not set, so the agents do not reason on this machine and every handling stays in
guided mode. That last one is the only remaining blocker to the system deciding
anything, and it is deliberate: without a model it refuses rather than guessing.
