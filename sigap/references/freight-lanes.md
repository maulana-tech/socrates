# Freight lanes and what they cost

> Transit time and container rates for the lanes this installation imports on.
> Used to price an option, and to say out loud when a price is not knowable.
>
> Compiled 15 October 2026. Confidence marks as in `tkdn-rules.md`.

---

## Container rates, as assessed 8 October 2026

**OFFICIAL.** Drewry's World Container Index, the assessment published
Thursday **8 October 2026**:

| Lane | USD per 40ft |
|---|---|
| **Composite (global)** | **4,351** |
| Shanghai to Los Angeles | 7,624 |
| Shanghai to New York | 10,220 |
| Shanghai to Rotterdam | 3,337 |
| Shanghai to Genoa | 3,696 |

**The lane we need is not in it.** The WCI covers eight major east-west
trades. There is no Shanghai or Ningbo to Jakarta line in it, because
intra-Asia is not one of them. So the composite is the nearest published
anchor for this installation's main lane, and it is an anchor, not a quote.

This matters more than it looks. A planner that wants a rupiah figure for
switching a shipment has no live index for its own lane, which under this
system's own rule means it must not emit one. The honest output is a range
with the anchor named, or a quotation request.

## Transit time, Ningbo or Shanghai to Tanjung Priok

**ASSUMED, and the published figures are far apart.**

| Figure | What it is | Weight |
|---|---|---|
| **8 days** Shanghai to Jakarta | APL's CS8 weekly direct service, port to port | plausible, undated article |
| 11 days Shanghai to Surabaya | same service | same |
| 20 to 35 days | aggregator, Ningbo origin | low, poor-quality page |
| 25 to 30 days | aggregator, Shanghai to Priok | low, poor-quality page |

The spread is not noise, it is two different measurements. A weekly direct
intra-Asia string genuinely runs single-digit days port to port. The 25 to 30
day claims almost certainly describe door to door, including consolidation,
booking wait and inland legs, and a booking wait is real but it is not transit.

**Plan on 10 days port to port** for a direct service, and add the booking
wait and Priok dwell as separate lines rather than folding them in. Dwell is
in `priok-dwell-time.md` at 5 days for imports and is **added** to transit.

So a realistic Ningbo to plant door estimate is 10 transit + 5 dwell + inland,
not a single number, and a shipment that looks 3 days clear of a stockout on
transit alone is already late.

## What a forced reroute adds

**SECONDARY.** From the Red Sea diversions of 2024, the only recent episode
with published lane-by-lane numbers (detail in `disruption-precedents.md`):
7 to 18 days added depending on the lane, about +50% on Asia-Europe.

Two cautions carry over to any reroute this system prices:

1. The operating cost of the longer voyage was estimated at **USD 100 to 150
   per TEU**, while rates on the affected lanes rose by up to **284%**. Almost
   all of the cost was scarcity, not distance.
2. Berthing wait at Priok is reported at 18 to 36 hours in normal conditions,
   and April 2025 shows what it becomes when arrivals converge.

## Parameters

<!-- Read by tools/compliance.py and simulation. Keep key: value, one per line. -->

```
wci_composite_usd_per_40ft: 4351
wci_assessed_on: 2026-10-08
cnngb_idtpp_transit_days: 10
cnngb_idtpp_transit_confidence: ASSUMED
priok_berth_wait_hours_low: 18
priok_berth_wait_hours_high: 36
reroute_added_days_low: 7
reroute_added_days_high: 18
intra_asia_index_published: false
```

## Sources

- [Drewry World Container Index](https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry) (OFFICIAL, assessed 8 October 2026)
- [Seatrade Maritime: APL boosts Indonesia connectivity with new China Southeast Asia service](https://www.seatrade-maritime.com/containers/apl-boosts-indonesia-connectivity-with-new-china-southeast-asia-service)
- [Alibaba seller guide: FCL shipping China to Indonesia](https://seller.alibaba.com/blogs/2026/southeast-asia/logistics/fcl-shipping-china-indonesia-port-customs-guide-alibaba)
- [AJOT / Freightos: Red Sea diversion delays and rates](https://ajot.com/news/freightos-weekly-update-red-sea-diversion-causing-delays-and-climbing-rates)
- [Seko Logistics: global canal impact update](https://www.sekologistics.com/en/resource-hub/news/client-advisory-global-canal-impact-update-february-1-2024/)

**Not yet done:** confirm the APL CS8 service still runs and get a dated
schedule, which would promote `cnngb_idtpp_transit_days` from ASSUMED. An
intra-Asia container index subscription would remove the need to anchor this
installation's main lane on a global composite.
