# USD to IDR

> One rate, with its date and its source. Purchase orders from foreign
> suppliers carry prices in their own currency and every rupiah comparison
> needs a stated rate.
>
> Compiled 15 October 2026. Confidence marks as in `tkdn-rules.md`.

---

## The rate

**SECONDARY.** Bank Indonesia's JISDOR reference rate, as reported by Kontan:

```
Friday 7 October 2026    Rp 18,069 per USD    (up 0.12% from Rp 18,090)
```

**Sources disagree on the days around it,** and the disagreement is larger
than the daily move, so it is recorded rather than smoothed:

| Date | Rate | Reported by |
|---|---|---|
| 2 October 2026 | 17,898 | Kiakrikil |
| 6 October 2026 | 17,917 | JournalArta |
| **7 October 2026** | **18,069** | **Kontan** |

Kontan's own report says the previous day was 18,090, which cannot be
reconciled with 17,917 for 6 October. One of the two is wrong and neither has
been checked against Bank Indonesia's own publication.

The Kontan figure is used because it is a dated market report that states both
the level and the prior day. It is marked SECONDARY precisely because of the
contradiction above.

## Why a single stated rate, and not a live feed

A converted figure is only as honest as the rate behind it, so the rate is a
parameter with a date attached rather than a number compiled into the code. A
rupiah comparison made on a rate nobody stated is the kind of figure this
system refuses elsewhere, and it would be inconsistent to allow it here.

**This rate goes stale.** The rupiah moved from 16,879 in March 2026 to 18,069
in October 2026, about 7% in seven months. A figure converted on a rate from
weeks ago carries that error, so every converted amount reports the rate and
the date it came from, and `fx_as_of` is what tells an operator to refresh it.

## Parameters

<!-- Read by tools/fetcher through tools/compliance.rule_params. -->

```
usd_idr: 18069
fx_as_of: 2026-10-07
fx_source: JISDOR via Kontan
fx_confidence: SECONDARY
fx_stale_after_days: 30
```

## Sources

- [Kontan: rupiah JISDOR 7 October 2026](https://investasi.kontan.co.id/news/rupiah-jisdor-menguat-012-ke-rp-18069-per-dolar-as-pada-jumat-107)
- [Kontan: rupiah JISDOR 1 September 2026, Rp 17,727](https://investasi.kontan.co.id/news/rupiah-jisdor-menguat-011-ke-rp-17727-per-dolar-as-pada-selasa-192026)
- [Kontan: rupiah JISDOR 10 March 2026, Rp 16,879](https://investasi.kontan.co.id/news/rupiah-jisdor-menguat-055-ke-rp-16879-per-dolar-as-pada-selasa-1032026)

**Not yet done:** read the rate from Bank Indonesia's own JISDOR publication
and promote it from SECONDARY. Until then the contradiction above stands, and
a converted figure should be read as carrying roughly 1% of rate uncertainty
on top of everything else.
