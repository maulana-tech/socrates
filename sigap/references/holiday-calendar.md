# Indonesian public holidays, for counting working days

> A permit that takes ten working days does not take ten working days across
> Idul Fitri. Kira counts working days against this file, so a licence estimate
> that straddles a holiday cluster stops being optimistic.
>
> Compiled 15 October 2026. Confidence marks as in `tkdn-rules.md`.

---

## What this is

**SECONDARY.** National holidays and collective leave for 2027 are set by a
joint decree of three ministers, the SKB 3 Menteri, signed 15 September 2026 by
the Ministers of Religious Affairs, Manpower, and Administrative Reform, and
announced by the Coordinating Ministry for Human Development and Culture.
**18 national holidays and 8 days of collective leave**, 26 days in total.

**The sources disagree on detail, and that matters here.** The decree number is
given as 1205, 3 and 2 of 2026 by Kemenko PMK and Setneg, while one outlet
writes the third as 5. Collective leave dates around Idul Fitri are reported as
9, 12 and 15 March by two outlets, and other sources place Iduladha and Waisak
leave on different days again. The dates below are the national holidays, where
agreement is good. **Collective leave is deliberately not listed**: the sources
do not agree, and a working-day count built on a date nobody can confirm is
worse than one that ignores leave and says so.

## 2027 national holidays

<!-- Read by tools/compliance.py. One ISO date per line, reason after a space. -->

```
2027-01-01 Tahun Baru Masehi
2027-01-05 Isra Mikraj
2027-02-06 Tahun Baru Imlek
2027-03-08 Hari Suci Nyepi
2027-03-10 Idul Fitri 1448H
2027-03-11 Idul Fitri 1448H
2027-03-26 Wafat Yesus Kristus
2027-03-28 Paskah
2027-05-01 Hari Buruh
2027-05-06 Kenaikan Yesus Kristus
2027-05-17 Iduladha
2027-05-20 Waisak
2027-06-01 Hari Lahir Pancasila
2027-06-06 Tahun Baru Islam 1449H
2027-08-15 Maulid Nabi
2027-08-17 Proklamasi Kemerdekaan
2027-12-25 Hari Natal
```

That is 17 dates against the 18 the decree is reported to contain, so **one is
missing from the press coverage used here.** It is recorded as a known hole
rather than padded out with a guess.

## Why a planner should care

The March cluster is the one that breaks schedules. Nyepi on 8 March, Idul
Fitri on 10 and 11 March, then Good Friday on 26 March and Easter on 28 March
puts four holidays plus unconfirmed collective leave into a single month. A ten
working day permit started in early March can land in April.

## Sources

- [Kemenko PMK: 18 national holidays and 8 collective leave days for 2027](https://www.kemenkopmk.go.id/pemerintah-tetapkan-18-hari-libur-nasional-dan-8-cuti-bersama-tahun-2027) (OFFICIAL)
- [Setneg: the 2027 joint decree](https://setneg.go.id/baca/index/inilah_skb_3_menteri_libur_nasional_dan_cuti_bersama_2027) (OFFICIAL)
- [Hukumonline: list of 2027 national holidays and collective leave](https://www.hukumonline.com/berita/a/Daftar-libur-nasional-2027%20-lt6aaa6070150ec/)
- [Detik: the 2027 decree, how long is Lebaran](https://www.detik.com/jogja/berita/d-8663540/daftar-libur-nasional-cuti-bersama-di-skb-3-menteri-2027-lebaran-berapa-hari)

**Not yet done:** download the decree itself from Kemenko PMK, settle the
eighteenth date, and add collective leave once the dates are confirmed.
