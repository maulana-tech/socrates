# Industry disruption precedents

> What has actually happened to supply chains like this one, with dates and
> numbers. This is **not** this company's own history: `search_past_incidents`
> reads the operator's finished runs, and nothing here belongs in that table.
> Writing these in as runs would invent an operational record, which is the one
> thing this system exists to refuse.
>
> Compiled 15 October 2026. Confidence marks as in `tkdn-rules.md`.

---

## Why a library of four

Each of these is here because it breaks a different assumption the planner
would otherwise make quietly:

| Precedent | The assumption it breaks |
|---|---|
| Aisin 1997 | that a qualified second source exists when you need it |
| Ningbo 2021 | that a port either works or does not |
| Tanjung Priok 2025 | that arrival slips are independent of each other |
| Red Sea 2024 | that the cost of a reroute is the cost of the extra distance |

The fourth is the one that most changes a rupiah figure, and the third is the
one this system currently gets wrong.

---

## 1. Aisin Seiki fire, 1 February 1997

**SECONDARY.** A fire before dawn destroyed Factory No. 10 at Kariya, Aichi.
The plant made proportioning valves (P-valves), a brake component costing a
few dollars.

- Roughly **99% of Toyota's P-valves** came from that one plant, the remaining
  1% from Nissin Kogyo.
- Just-in-time meant Toyota's assembly plants held about **four hours** of them.
- **18 assembly plants in Japan stopped for almost a week.** Cost put at
  **USD 195 million**.
- Toyota had been running against its own double-sourcing policy on this part.
- Recovery was faster than the damage implied: around 200 suppliers
  re-tooled to make P-valves without a contract or an agreed price.

**Careful here:** one history says the plant made ~99% of P-valves, another
says it supplied "almost 90 percent of major brake parts". Those are different
scopes and must not be merged into one number.

**What it means for us.** The exposure scan currently finds **88 materials
with a single source**. Aisin is what that number costs when it goes wrong,
and the interval between the fire and the first idle line was hours, not days.
It also sets the ceiling on the optimistic reading: Toyota survived because it
had thirty years of supplier relationships to call on, which is not a control
a planner can exercise on the day.

```
id: aisin-1997
title: Fire destroys the sole plant making Toyota's P-valves
date: 1997-02-01
kind: supplier_outage
mechanism: single-sourced low-value part, four-hour buffer downstream
halt_days: 6
cost_usd_m: 195
concentration_pct: 99
confidence: SECONDARY
lesson: a part's unit cost says nothing about its stoppage cost. Rank single sourcing by hours of cover, not by spend.
```

## 2. Ningbo-Zhoushan, Meidong terminal, August 2021

**SECONDARY.** One dock worker tested positive for COVID-19 and the Meidong
terminal stopped on **11 August 2021**, inbound and discharge included. Other
terminals at Ningbo tightened entry at the same time.

- Container ships resumed berthing at the Meishan Island terminal on
  **24 August 2021**, about two weeks after the stoppage.
- The outer anchorage queue went from about 30 ships on 10 August to about
  **40 on 12 August**; one AIS-based count put it near 50 while the port
  authority said it was running at 90% capacity.
- **CMA CGM** rerouted vessels to Shanghai or omitted Ningbo; **Hapag-Lloyd**
  warned of delays to planned sailings.
- **Typhoon In-fa had already slowed** Ningbo-Zhoushan and Shanghai in late
  July, so the closure landed on a port that was already behind.
- Observers judged it much smaller than the roughly month-long Yantian
  curtailment earlier in 2021.

**Duration is contested.** One advisory expected a phased reopening from
18 August, no new cargo until 25 August, and normal operations from
1 September, and labelled its own timeline unconfirmed. The berthing-resumed
date of 24 August is the firmer of the two. Plan against the range, not the
midpoint.

**What it means for us.** This is the real version of the scenario this system
runs. Three things in it are worth copying into any Ningbo estimate: the
trigger was one positive test rather than a storm, the port stayed **partly**
open rather than closing, and a prior typhoon had already consumed the slack.
A model that treats a port as open or shut will read 90%-of-capacity as fine.

```
id: ningbo-meidong-2021
title: One COVID case closes Ningbo's Meidong terminal
date: 2021-08-11
kind: port_closure
port: CNNGB
mechanism: single terminal suspended, rest of port degraded not closed
closure_days_low: 13
closure_days_high: 21
queue_vessels: 40
confidence: SECONDARY
lesson: a port is not a switch. Degraded capacity with a queue is the normal case, and a prior weather event removes the buffer that makes it survivable.
```

## 3. Tanjung Priok landside gridlock, April 2025

**SECONDARY.** Three container ships, **MSC Adu V**, **Ever Balmy** and
**Starship Venus**, arrived late at New Priok Container Terminal 1, two about
a week behind schedule and one a day late. They were worked at the same time.

- Discharge passed **4,000 TEU in a day** against the terminal's normal
  2,000 to 2,500.
- Truck entries reached about **4,200 a day** against roughly 2,500 normally.
- Pelindo expected the backlog cleared by **Sunday 20 April**.
- Jakarta's governor apologised publicly, called the planning unprofessional,
  and had a formal warning issued to Pelindo.

**Cause is disputed.** Pelindo linked it partly to late docking at NPCT1 and
partly to the lifting of the post-Eid truck restriction over a long weekend.
A separate account says Pelindo and the Transport Ministry concluded the Eid
restriction was **not** the cause, pointing instead to three simultaneous
dockings, yard density, and receiving and delivery trucks being handled
together beyond equipment capacity.

**What it means for us, and it is a correction.** Our arrival model slips each
shipment on its own. This event is what happens when slips **correlate**: a
delay upstream does not stay upstream, it converges at the destination and
becomes a second, landside delay that no shipment's own schedule predicts.
Two vessels a week late plus one a day late produced a port-wide jam, and the
containers on a punctual third vessel were stuck behind it. Any Priok dwell
figure taken from a quiet week understates the week that matters.

```
id: priok-npct1-2025
title: Three late vessels converge and jam Tanjung Priok
date: 2025-04-16
kind: port_congestion
port: IDTPP
mechanism: correlated upstream delay, simultaneous discharge, landside capacity exceeded
clearance_days: 4
teu_per_day_peak: 4000
teu_per_day_normal: 2250
confidence: SECONDARY
lesson: arrival slips are correlated, not independent. Model convergence at the destination port, and add dwell on top of transit rather than inside it.
```

## 4. Red Sea diversions, from December 2023

**SECONDARY.** Attacks on shipping pushed carriers off the Suez route and
around the Cape of Good Hope. By **1 February 2024, 80%** of containerships
on the Suez route had diverted.

Added transit time, by source, because they do not agree and the spread is
lane-dependent rather than random:

| Source | Added days |
|---|---|
| Freightos | 7 to 14, lane-dependent |
| Linerlytica | North Europe +7, West Med +10, East Med +18 |
| Fitch | 10 to 15 via the Cape, about +50% on Asia-Europe |

What the money did:

- Asia-Europe rates **+284%**; the World Container Index **+151%** against
  October 2023 (Fitch).
- Shanghai to Rotterdam **+158% year on year** as of 8 February 2024 (Drewry).
- The incremental cost of the Cape diversion itself was estimated at only
  **USD 100 to 150 per TEU**, far below what rates rose by.

**What it means for us, and it changes a number.** The operating cost of
sailing further was roughly two orders of magnitude smaller than the price
move. A disruption-period quote is mostly scarcity rent, not distance. So
`ExtraCost` on an option sourced during a disruption should not be read as the
cost of the longer route, and a freight figure pulled from a spot index while
the disruption is running is not a forecast of what it will cost to repeat.

```
id: red-sea-2024
title: Suez diversions reroute Asia-Europe around the Cape
date: 2023-12-15
kind: lane_closure
mechanism: route denied, capacity absorbed by longer voyages, spot rates repriced
added_days_low: 7
added_days_high: 18
reroute_cost_usd_per_teu: 125
rate_rise_pct: 284
confidence: SECONDARY
lesson: separate the operating cost of a reroute from the scarcity price of capacity. Quote one, do not infer the other.
```

## Parameters

<!-- Read by tools/precedent.py. Keep key: value, one per line. -->

```
precedent_count: 4
single_source_halt_hours: 4
port_degraded_not_closed: true
arrival_slips_correlated: true
reroute_cost_usd_per_teu: 125
precedent_confidence: SECONDARY
```

## Sources

- [Wikipedia: 1997 Aisin fire](https://en.wikipedia.org/wiki/1997_Aisin_fire)
- [Funding Universe: Aisin Seiki company history](https://www.fundinguniverse.com/company-histories/aisin-seiki-co-ltd-history/)
- [S&P Global: COVID-19 infection halts Ningbo container terminal](https://www.spglobal.com/energy/en/news-research/latest-news/shipping/081121-covid-19-infection-halts-ningbo-container-terminal-further-straining-supply-chain)
- [S&P Global: container ships resume berthing at Ningbo terminal](https://www.spglobal.com/energy/en/news-research/latest-news/shipping/082421-container-ships-resume-berthing-at-ningbo-terminal-closed-for-quarantine)
- [PSA BDP / Reuters: carriers divert vessels from Ningbo](https://psabdp.com/news/carriers-divert-vessels-from-ningbo-as-fears-of-another-yantian-grow)
- [Investor Trust: severe truck congestion at Indonesia's busiest port](https://investortrust.id/business/63322/severe-truck-congestion-at-indonesias-busiest-port-sparks-urgent-reform-calls)
- [Investor Trust: Jakarta governor apologises for the Tanjung Priok jam](https://investortrust.id/market/63284/jakarta-governor-apologizes-for-severe-traffic-jam-at-tanjung-priok-port)
- [Seatrade Maritime: Indonesia cracks the whip on Tanjung Priok congestion](https://www.seatrade-maritime.com/shipping-finance/indonesia-cracks-the-whip-on-tanjung-priok-congestion)
- [AJOT / Freightos: Red Sea diversion causing delays and climbing rates](https://ajot.com/news/freightos-weekly-update-red-sea-diversion-causing-delays-and-climbing-rates)
- [Fitch via East & Partners: Red Sea disruptions hike shipping costs](https://eastandpartners.com/publications/banking-news/red-sea-disruptions-hike-shipping-costs-fitch)
- [Seko Logistics: global canal impact update, 1 February 2024](https://www.sekologistics.com/en/resource-hub/news/client-advisory-global-canal-impact-update-february-1-2024/)

**Not yet done:** the Aisin figures are from secondary histories. The primary
account is Nishiguchi and Beaudet in Sloan Management Review (1998) and it has
not been read, so `halt_days: 6` stays SECONDARY. No precedent here is
Indonesian except Priok 2025; a domestic supplier-fire or flood case would be
worth more to this installation than Red Sea 2024.
