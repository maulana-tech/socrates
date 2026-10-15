# Tanjung Priok dwell time

> How long a container actually sits at the port before it moves. It is added
> to transit, not contained in it, so an option that arrives three days before
> a stockout arrives late once dwell is counted.
>
> Compiled 15 October 2026. Confidence marks as in `tkdn-rules.md`.

---

## The figures, and why they disagree

**SECONDARY.** Published numbers span two to five and a half days, and the
spread is not noise: they measure different things.

| Figure | What it covers | When |
|---|---|---|
| **2.85 days** | National average across Priok, Belawan, Makassar, Tanjung Emas and Tanjung Perak | 2026 |
| **5.5 days** | Priok, **import containers only**, seven-year average | academic, undated |
| 3.5 days | Priok, quoted by the Transport Minister | 2016 |
| 3 days | Priok, later ministry reporting | post-2016 |

The 2.85 figure is the one usually quoted, and it is the least applicable here:
it averages five ports and all traffic. The 5.5 figure is the one that matches
what this system plans, **imported containers at Priok**, and it is the
pessimistic end.

## What to plan against

**ASSUMED.** Plan imports at **5 days** and treat anything under 3 as a bonus
that has not happened yet.

The reasoning is asymmetric cost, not pessimism for its own sake. Planning at
2.85 and getting 5.5 means a stockout. Planning at 5 and getting 3 means two
days of extra cover. One of those errors is recoverable and the other is a
production line stopping, so the estimate leans toward the recoverable one.

## Parameters

<!-- Read by tools/compliance.py. Keep key: value, one per line. -->

```
priok_import_dwell_days: 5
priok_optimistic_dwell_days: 3
national_average_dwell_days: 2.85
dwell_confidence: ASSUMED
```

## Sources

- [DDTCNews: dwell time targeted down to 2.85 days](https://news.ddtc.co.id/berita/nasional/1817834/dwelling-time-ditarget-susut-jadi-285-hari-tahun-ini)
- [Integration of dwelling time and container handling at Tanjung Priok](https://journal.itltrisakti.ac.id/index.php/jmtranslog/article/download/265/pdf)
- [Kemenhub: helpdesk formed at Tanjung Priok to reduce dwelling time](https://kemenhub.go.id/post/read/upaya-turunkan-dwelling-time,-kemenhub-bentuk-helpdesk-di-pelabuhan-tanjung-priok) (OFFICIAL)
- [Media Indonesia: Tanjung Priok as the dwelling time example](https://mediaindonesia.com/ekonomi/67624/tanjung-priok-jadi-contoh-dwelling-time)

**Not yet done:** get a current Priok-only import figure from Pelindo or INSW
and promote the planning number from ASSUMED.
