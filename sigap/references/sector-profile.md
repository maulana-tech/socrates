# Indonesian automotive sector, as published

> The figures behind the reference installation's profile. Every number here
> is from a public source, so that the profile shipped with this system is a
> documented sector position rather than an invented company.
>
> Compiled 15 October 2026. Confidence marks as in `tkdn-rules.md`.

---

## Why this document exists

The profile used to name an invented company, **PT Karya Presisi Nusantara**,
with invented figures: 340 active materials, 61% of raw material value
imported. Nothing cited it, and because `profile()` ignored uploads, those
numbers were applied to every installation no matter whose data was loaded.

A named real manufacturer would be worse, not better. Attaching invented stock
levels and an invented TKDN breach to a listed company is a fabricated record
about a real firm. So the profile is now what it actually is: a **reference
installation** whose parameters come from the published sector figures below,
replaced by the operator's own upload the moment one exists.

## Market size

**SECONDARY** (Gaikindo figures as reported, not from Gaikindo's own release).

| 2025 | Units | Change |
|---|---|---|
| Wholesales (factory to dealer) | **803,687** | -7.2% from 865,723 in 2024 |
| Retail (dealer to customer) | **833,692** | -6.3% from 889,680 in 2024 |
| December 2025 alone | 94,100 | +26.9% from November's 74,131 |

Gaikindo's 2025 target had been 900,000 units. Leading brands by wholesales:
Toyota **250,431**, Daihatsu **130,677**, Mitsubishi Motors **71,781**.

The December spike is attributed to manufacturers clearing 2025 stock with
promotions. It matters here because a demand figure read off December
overstates the run rate by about a quarter.

## Import dependence, and the numbers do not agree

**SECONDARY.** This is the single most important parameter for a disruption
system, and the published figures range from 60% to 91.7%, because they
measure different things. They must not be averaged.

| Figure | What it measures | Source |
|---|---|---|
| **91.7%** | dependence of automotive **export products** on imported raw materials, five-year window, worst of any sector, heaviest in transmission components and spare parts | BPPP, Ministry of Trade, via Kompas |
| 90% | share of **raw materials** met from imports | GIAMM secretary general |
| 80% | **component** imports | Ministry of Industry |
| ~80% / ~90% | **local** component use, four-wheel / two-wheel | GIAMM chair |
| ~60% | TKDN achievable on locally sourced raw material | Minister of Industry (Airlangga, older) |

The last two look like contradictions of the first three and are not: local
*component* content can be high while the *raw material* inside those
components is imported. A stamped bracket made in Karawang from imported coil
is local content and an import exposure at the same time. That distinction is
the whole reason this system separates TKDN from lane risk.

**The reference installation uses 91.7%** for imported raw material value,
because it is the most specific published figure, is attributed to a ministry
research body, and is measured on exactly the population this installation
represents: an automotive exporter's raw material base.

## Steel, the main imported input

**SECONDARY**, BPS data as quoted by the Minister of Trade, February 2026.

- HS 72 (iron and steel) imports, 2025: **USD 9.53 billion**
- HS 72 exports, 2025: USD 27.97 billion, surplus USD 18.44 billion
- December 2025 HS 72 import value by port of entry: USD 2.28 billion, with
  DKI Jakarta first at **USD 977.27 million**

Indonesia is a large net exporter of iron and steel and still imports
USD 9.5 billion of it, because the grades differ. The exports are largely
processed nickel-bearing stainless, and the automotive-grade flat and spring
steels are the imports. A sector-level trade surplus is therefore no comfort
to a Tier-1 at all, and reading one as supply security is the mistake this
figure is recorded to prevent.

Jakarta being the largest port of entry by value is consistent with
Tanjung Priok carrying this installation's steel exposure.

## Real Tier-1 reference points

**SECONDARY.** Published figures from listed Indonesian Tier-1 suppliers,
kept here as sector calibration. None of this licenses attributing invented
stock, orders or compliance positions to these companies.

**PT Dharma Polimetal (DRMA)**, founded 1989, plants at Jababeka and Bekasi:

- H1 2026 revenue Rp 3.157 trillion, +14% on H1 2025's Rp 2.773 trillion;
  net profit Rp 282.9 billion, +17.8%
- 9M 2025 revenue Rp 4.39 trillion, +9.20%
- **Exports 0.5% of sales.** Domestic Rp 4.37 trillion against exports of
  Rp 18.36 billion, 9M 2025
- **Largest customer PT Astra Honda Motor at Rp 2.37 trillion** of 9M 2025
  revenue, roughly 54%

**PT Astra Otoparts (AUTO)**: 2025 revenue about Rp 19.9 trillion (+4.37%),
net profit about Rp 2.2 trillion (+8.43%), a record. Joint ventures include
GS Battery, Akebono Brake Astra Indonesia, KYB Indonesia and Inti Ganda
Perdana.

**PT Indospring (INDS)**, Gresik, East Java, founded 1978, leaf and coil
springs and stabiliser bars: 2017 net sales Rp 1.96 trillion, with Mitsubishi
Steel Mfg at 21.25% of sales value and Kramayudha Tiga Berlian at 13.13%.
Headcount 2,553.

**The pattern worth copying into the profile** is concentration on both sides.
DRMA earns about half its revenue from one customer and sells 0.5% abroad;
INDS had a fifth of sales with one counterparty. A Tier-1 here is not
diversified, so a disruption has one place to land, and an OEM delivery
penalty is not a line item, it is the business.

## What the reference installation therefore assumes

| Profile field | Value | Where it comes from |
|---|---|---|
| `ImportedRawMaterialPct` | 91.7 | BPPP Ministry of Trade, above |
| `TkdnContractFloorPct` | 40.0 | Permenperin 35/2025 staged target to 2026, see `tkdn-rules.md` |
| `TkdnCurrentPct` | 38.2 | **ASSUMED.** A position just under the floor, so the compliance veto is exercised rather than decorative |
| `Facilities` | Karawang, Surabaya, Tanjung Priok | real places, real coordinates |

Only `TkdnCurrentPct` is a scenario choice, and it is chosen to be the
awkward case. It is labelled, and an uploaded profile replaces it.

## Parameters

<!-- Read by tools/compliance.py. Keep key: value, one per line. -->

```
imported_raw_material_pct: 91.7
imported_raw_material_confidence: SECONDARY
sector_wholesales_2025: 803687
sector_wholesales_2024: 865723
hs72_import_usd_bn_2025: 9.53
customer_concentration_observed_pct: 54
export_share_observed_pct: 0.5
```

## Sources

- [CNBC Indonesia: 2025 car sales data](https://www.cnbcindonesia.com/news/20260112105152-4-701503/penjualan-mobil-2025-turun-parah-ini-datanya)
- [Fortune IDN: best-selling brands of 2025](https://www.fortuneidn.com/business/merek-mobil-terlaris-sepanjang-2025-di-indonesia-d7w03-00-fykp7-llpqlp)
- [Kompas: high dependence on imported raw materials](https://www.kompas.id/artikel/ketergantungan-impor-bahan-baku-tinggi) (BPPP Ministry of Trade)
- [Ministry of Industry: automotive industry dependence on imported components](https://kemenperin.go.id/artikel/4239/Industri-Otomotif-Ketergantungan-Komponen-Impor) (OFFICIAL)
- [Ministry of Industry: component industry still imports raw materials](https://www.kemenperin.go.id/artikel/11433/Toyota:-Industri-Komponen-Masih-Impor-Bahan-Baku) (OFFICIAL)
- [Republika: raw material problems hold back the component industry](https://ekonomi.republika.co.id/berita/ekonomi/korporasi/19/08/14/pw6efc383-industri-komponen-otomotif-ri-terhambat-masalah-bahan-baku)
- [IDX Channel: iron and steel trade surplus USD 18.44 billion in 2025](https://www.idxchannel.com/economics/perdagangan-besi-dan-baja-ri-catat-surplus-usd1844-miliar-di-2025-2026)
- [Databoks: iron and steel import value by port, HS 72](https://databoks.katadata.co.id/en/mining/multiple/69000cf6e402da4/import-value-statistics-for-iron-and-steel-from-ports-with-hs-code-72-period-2018-2025)
- [IDN Financials: DRMA H1 2026 results](https://www.idnfinancials.com/news/66732/drma-posts-idr-282-9-billion-net-profit-in-h1-2026-up-17-8)
- [IDN Financials: Astra Otoparts record net profit](https://www.idnfinancials.com/news/61595/astra-otoparts-net-profit-reaches-idr-2-2-trillion-new-record-high)
- [IDN Financials: PT Indospring profile](https://www.idnfinancials.com/INDS/PT-Indospring-Tbk)

**Not yet done:** every market and dependence figure here is press-reported
rather than read out of Gaikindo's own release or a BPS table, so they stay
SECONDARY. The 91.7% figure in particular is load-bearing and deserves the
primary BPPP publication. Import share by country of origin for HS 7208 and
7606 is not available free and is the gap that keeps lane concentration
qualitative.
