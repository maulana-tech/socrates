# LARTAS: what an import licence costs in days

> Larangan dan/atau Pembatasan, Indonesia's import prohibition and restriction
> regime. Kira uses this to judge whether an imported option can clear customs
> in time to be worth choosing.
>
> Compiled 15 October 2026. Confidence marks mean the same as in
> `tkdn-rules.md`: OFFICIAL, SECONDARY, ASSUMED.

---

## 1. What LARTAS is

**OFFICIAL.** Two categories, and the difference decides everything:

- **Dilarang**, prohibited. Cannot be imported under any condition. There is no
  licence, no lead time, no workaround. An option resting on a prohibited item
  is not expensive, it is impossible.
- **Dibatasi**, restricted. Importable, but only against a permit from the
  responsible ministry. This is a schedule problem, not a yes-or-no problem,
  and the right question is how many working days the permit takes.

Most of what a Tier-1 automotive manufacturer imports falls in the second
category, which is why this file is mostly about days.

## 2. How to find out, authoritatively

**OFFICIAL.** The determination is per **HS code**, not per material name, and
the authority is the **INSW portal** at <https://insw.go.id>. Enter the HS code
and read the LARTAS section. A named ministry there means the item is
restricted and that ministry issues the permit.

Nothing in this file overrides an INSW lookup for a specific shipment. This is
planning guidance; INSW is the determination.

## 3. Steel and iron

**SECONDARY.** At least **298 HS codes** covering iron, steel and derivatives
are subject to LARTAS, per Keputusan Menteri Keuangan 23/KM.4/2022. The
importer must hold:

| Document | What it is |
|---|---|
| **Persetujuan Impor (PI)** | Import approval, Ministry of Trade |
| **Laporan Surveyor (LS)** | Pre-shipment inspection report |

The approval regime is set out in Permendag 110/2018, amended by Permendag
3/2020. Both may have been amended again; check before relying on either.

## 4. Aluminium

**ASSUMED, and this is the weakest line in the file.**

Aluminium alloy sits under **HS heading 7601**, with `7601.20` covering
aluminium alloys as against `7601.10` for unalloyed. That heading is the
international standard and is safe. What is **not** established is Indonesia's
8-digit subdivision or whether the specific subcode carries a LARTAS
requirement: trade-data sites list `7601.20.10` and similar, but at least one
widely-cited page quotes Vietnamese customs codes and duty rates for what it
labels as Indonesian, so that family of sources cannot be trusted here.

**Before any real import decision, look the exact 8-digit code up in BTKI or
on INSW.** This project plans against the working figure below and says so.

## 5. Working days, which is what the planner actually needs

**ASSUMED.** Permit lead times used for planning:

| Situation | Working days |
|---|---|
| Established origin, existing PI on file | 0 |
| **New origin country, PI needed** | **10** |
| New origin plus Laporan Surveyor | 15 |

Ten working days is roughly two calendar weeks, and it lands on top of transit,
not inside it. An option that arrives four days before a stockout and needs a
new-origin permit does not arrive four days early. It arrives six days late.
That arithmetic is the whole reason this file exists.

Working days exclude weekends. Indonesian public holidays are handled
separately in `holiday-calendar.md`, which is not written yet, so a permit
estimate that straddles Idul Fitri or the year-end cluster is currently
optimistic.

## Parameters

<!-- Read by tools/compliance.py. Keep key: value, one per line. -->

```
new_origin_working_days: 10
new_origin_with_surveyor_working_days: 15
established_origin_working_days: 0
aluminium_hs_heading: 7601.20
aluminium_hs_confidence: ASSUMED
determination_source: https://insw.go.id
```

## Sources

- [Bea Cukai Jakarta: about LARTAS](http://bcjakarta.beacukai.go.id/perizinan/tentang-lartas/119-perizinan-lartas.html) (OFFICIAL)
- [Kemenkeu learning centre: checking LARTAS via INSW](https://klc2.kemenkeu.go.id/kms/knowledge/cara-mengetahui-ketentuan-lartas-barang-ekspor-impor-menggunakan-insw-590ee46f/detail/) (OFFICIAL)
- [Import requirements for iron and steel](https://ar-tek.co.id/impor-besi-dan-baja-apa-saja-syarat-utamanya/)
- [Documents for LARTAS imports: PI, LS, Pertek](https://imporekspor360.com/dokumen-lartas-impor/)
- [List of LARTAS import goods requiring a permit](https://asiacommerce.id/blog/daftar-barang-lartas-impor-yang-wajib-izin/)
- [HS heading 7601: aluminium ingots, billets, wire bars](https://www.seair.co.in/hs-codes/heading-7601-aluminium-ingots-billets-wire-bars.aspx)

**Not yet done:** confirm the aluminium 8-digit code and its LARTAS status on
INSW, and write `holiday-calendar.md` so permit estimates stop ignoring
Indonesian public holidays.
