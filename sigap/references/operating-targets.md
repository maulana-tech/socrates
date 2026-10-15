# Operating targets

> What the system is accountable to. Without a target an agent has nothing to
> optimise and can only react, so these are the numbers every planning
> decision is measured against.
>
> Compiled 15 October 2026. Confidence marks as in `tkdn-rules.md`.

---

## Why these are written down and not coded

A target in a Python constant is a target nobody reviewed. These belong to the
operations manager, not to the developer, and they are the one set of numbers
that should change without a deployment. The safety stock of every material in
the plant moves when `service_level_pct` moves, so the document that holds it
has to be the document that gets argued over.

## Service level

**ASSUMED, and it is a business choice, not a fact.**

`service_level_pct: 95` means: accept a 5% chance of running out during any
replenishment cycle. The multiplier that follows from it is the one the safety
stock formula uses.

| Service level | Multiplier (z) | What it means |
|---|---|---|
| 90% | 1.28 | runs out roughly one cycle in ten |
| **95%** | **1.65** | **the default here** |
| 98% | 2.05 | |
| 99% | 2.33 | roughly one cycle in a hundred |

95% is the usual automotive Tier-1 starting point, and it is deliberately not
99%: the stock needed rises much faster than the risk falls, and a Tier-1
running 99% on 340 materials has its working capital on the floor.

**Raise it per material, not globally.** A material whose stockout stops a
line with an OEM penalty deserves 99%; a consumable does not. That per-material
override is not built yet, so one number currently covers everything, which
is stated here rather than hidden.

## Cover and capital

**ASSUMED.**

```
min_cover_days: 14
```

The floor the old code applied to every material as its only policy. It stays,
but now as a **floor underneath** the calculated reorder point, not as the
policy itself. Where the calculation says less than 14 days, 14 wins, because
a formula is not a reason to hold less than two weeks of a part that stops a
line.

`inventory_cap_idr` and `expedite_budget_idr` are not set. They belong to the
customer's own finance position and this installation has no business
inventing them, so no total is enforced and the scorecard reports the figure
rather than judging it.

## Replenishment cadence

**ASSUMED.** `review_period_days: 1`. Stock is reviewed daily, so the formula
uses lead time alone rather than lead time plus a review period. If this
becomes a weekly review, the period has to be added to the exposure window or
the safety stock is understated by six days of demand.

## Parameters

<!-- Read by engine/planning.py through tools/compliance.rule_params. -->

```
service_level_pct: 95
service_level_z: 1.65
min_cover_days: 14
review_period_days: 1
order_cycle_days: 30
min_history_days: 30
min_lead_time_observations: 2
default_late_penalty_pct_per_day: 0.5
default_late_penalty_cap_pct: 10.0
supplier_slip_flag_days: 5
replenishment_top_n: 12
default_lead_time_days: 30
targets_confidence: ASSUMED
```

`order_cycle_days: 30` is how much demand one replenishment order should
carry beyond the reorder point. Ordering exactly up to the reorder point would
mean a new order almost every day, which no buyer and no supplier wants. It is
not an economic order quantity: that needs an ordering cost and a holding rate
this installation has not been given.

`min_lead_time_observations: 2
default_late_penalty_pct_per_day: 0.5
default_late_penalty_cap_pct: 10.0
supplier_slip_flag_days: 5
replenishment_top_n: 12` is the fewest delivered purchase orders needed
before a supplier's own lead time is measured instead of assumed. One delivery
is an anecdote and its spread is zero, which would read as a perfectly
reliable supplier.

`min_history_days: 30` is the shortest withdrawal history the planner will
compute a standard deviation from. Below it the spread is noise and the
planner says so instead of producing a number.

`default_lead_time_days: 30` applies only when a supplier has no delivered
purchase order to measure, and it is reported as an assumption every time it
is used.

## Late delivery terms

**ASSUMED, and they belong on the contract, not here.**

```
default_late_penalty_pct_per_day: 0.5
default_late_penalty_cap_pct: 10.0
supplier_slip_flag_days: 5
replenishment_top_n: 12
```

A standard SAP sales order carries no penalty clause, because the clause is in
the customer contract rather than in the order. So when an order arrives
without terms, these are used, and **every figure computed from them says it
used a default**. Half a percent a day capped at ten is the common shape of an
OEM delivery clause in this sector; the real numbers differ per customer and
per programme.

Treating a missing clause as zero would be worse than this default, because
zero reads as "being late to this customer is free", and an allocation that
believes that will cheerfully miss the order that costs the most.

## Cadences

**ASSUMED.**

```
supplier_slip_flag_days: 5
replenishment_top_n: 12
```

`supplier_slip_flag_days: 5` is the average slip, in days, above which a
supplier is raised in the weekly review. Below it a slip is noise in a sector
where ships are late; above it the pattern is the supplier.

`replenishment_top_n: 12` caps how many positions one daily review raises. The
cap exists for the same reason the exposure scan has one: a queue with ninety
items in it is a queue nobody reads, and the review reports the full count
alongside the twelve it raises.

## Sources

- Service level to z-multiplier is the standard normal table, not a source
  that needs citing.
- The 95% convention and the 14 day floor are practice, not regulation, and
  are marked ASSUMED for that reason.

**Not yet done:** per-material service levels, driven by whether a stockout
carries an OEM line-stop penalty. The penalty data is on the sales orders
already, so this is the next honest improvement.
