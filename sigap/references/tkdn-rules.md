# TKDN: local content rules that bind this portfolio

> Tingkat Komponen Dalam Negeri, the Indonesian local-content requirement.
> Kira rules on supply options against this file. A rejection written here is
> final and cannot be overturned on cost.
>
> Compiled 15 October 2026. **Every line carries how well it is sourced**, for
> the same reason every figure in this system carries an origin: a rule nobody
> can trace is a rule nobody can defend in an audit.

---

## Confidence, stated first

| Mark | Means |
|---|---|
| **OFFICIAL** | Traced to regulation text or a ministry portal |
| **SECONDARY** | Industry press or practitioner sources agree, official text not yet read |
| **ASSUMED** | This project's own working figure. Not a legal position |

Anything marked SECONDARY below must be checked against the full text at
JDIH Kemenperin before it is used for a real compliance decision. It is good
enough to reason with and not good enough to sign.

---

## 1. Which regulation applies

**SECONDARY.** The governing instrument is **Permenperin 35/2025**, which
updates the earlier TKDN and BMP certification regime set out in Permenperin
16/2011 and amended by Permenperin 25/2016. Industry reporting in late 2025
describes it as changing the calculation method rather than only the rates, so
figures quoted from pre-2025 sources are not safe to carry forward.

`Permenperin 16/2011` itself is **OFFICIAL** and readable, and is the source of
the structure below, but it is superseded.

## 2. How TKDN is calculated

**SECONDARY.** For a manufactured good, TKDN is the share of production cost
that is not foreign:

```
TKDN % = (production cost - foreign component cost) / production cost x 100
```

Cost is composed of three elements, weighted:

| Element | Weight |
|---|---|
| Direct material | 75% |
| Direct labour | 10% |
| Indirect factory overhead | 15% |

For direct material, the TKDN of each major component is multiplied by that
component's share of one finished unit, which is why a bill of materials is the
thing this calculation actually runs on, and why swapping one component's
source moves the number at all.

## 3. The thresholds that bind a Tier-1 automotive supplier

**SECONDARY.** Staged minimums reported for four-wheeled vehicles:

| Period | Minimum TKDN |
|---|---|
| 2019 - 2021 | 35% |
| **2022 - 2026** | **40%** |
| 2027 - 2029 | 60% |
| 2030 onward | 80% |

A separate **25%** floor appears in Permenperin 35/2025 for companies investing
in domestic manufacturing, reported via Gaikindo. It is a different threshold
for a different purpose and must not be read as replacing the table above.

**The 40% in force through 2026 is the floor this portfolio is contracted
against.** The step to 60% in 2027 is inside the planning horizon of any
sourcing decision made now with a multi-year supply agreement, and a decision
that satisfies 40% while making 60% unreachable is a decision that has moved
the problem rather than solved it.

## 4. What this means for a supply decision

Rules Kira applies, in order:

1. **An option must not worsen the position.** If current TKDN is above the
   floor, an option that drops it below the floor is blocked. If the portfolio
   is already below the floor, an option that lowers it further is blocked.
   Being below the floor does not forfeit every remaining option; making it
   worse is what is forbidden.
2. **Price never overturns rule 1.** A cheaper option that breaches is still
   blocked, and what the compliance cost is gets reported so the decision is
   visible rather than silent.
3. **An option that raises TKDN back above the floor is preferred** even at a
   premium, because the alternative is a contract breach rather than a cost.

## Parameters

<!-- Read by tools/compliance.py. Keep key: value, one per line. -->

```
contract_floor_pct: 40
floor_source: Permenperin staged minimum for 2022-2026 (SECONDARY)
floor_next_step_pct: 60
floor_next_step_from: 2027-01-01
direct_material_weight: 0.75
direct_labour_weight: 0.10
indirect_cost_weight: 0.15
```

## Sources

- [Permenperin 16/2011, full text](https://ukpbj.kemlu.go.id/uploads/laporan/20231124114226-peraturan-menteri.pdf) (OFFICIAL, superseded)
- [Gaikindo: new local content rules issued](https://www.gaikindo.or.id/aturan-baru-tingkat-komponen-dalam-negeri-untuk-industri-terbit/)
- [Kompas Otomotif: why TKDN matters to Indonesian automotive](https://otomotif.kompas.com/read/2025/10/02/070200415/mengapa-tkdn-krusial-dalam-industri-otomotif-indonesia)
- [Kompas Otomotif: TKDN rules change, incentives recalculated](https://otomotif.kompas.com/read/2025/11/17/070200415/regulasi-tkdn-berubah--hitung-ulang-insentif-industri-otomotif)
- [Calculating TKDN from major components](https://alatanindonesia.id/blog/cara-menghitung-nilai-tkdn-barang-berdasarkan-komponen-utama)
- [Overview of local content requirements in Indonesia](https://erepository.uwks.ac.id/11071/1/Local%20Content%20Requirements%20(LCR)_14062021.pdf)

**Not yet done:** read Permenperin 35/2025 in full from JDIH Kemenperin and
promote sections 1 to 3 from SECONDARY to OFFICIAL.
