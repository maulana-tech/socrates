# Rencana: dari respons gangguan ke menjalankan rantai pasok

> Disusun 15 Oktober 2026. Demo day 31 Oktober 2026, **tersisa 16 hari**.
> Rencana ini dibatasi supaya muat di 16 hari, bukan rencana enam bulan.
>
> **Status 15 Oktober 2026: Fase 0 sampai 5 sudah dibangun.** Yang tersisa
> Fase 6 (pengerasan) dan tampilan paralel untuk rekan tim. Arsitekturnya
> dijelaskan di `ARCHITECTURE.md`.

---

## Pergeseran intinya

Hari ini SIGAP bekerja begini: ada kejadian, sistem bereaksi, keluar
rekomendasi, orang menyetujui, selesai. Sekali jalan, lalu diam.

Menjalankan rantai pasok butuh tiga hal yang sekarang belum ada:

1. **Target yang harus dipenuhi.** Tanpa target, agen tidak punya yang
   dioptimalkan dan hanya bisa bereaksi. Target: tingkat layanan ke pelanggan,
   hari cadangan minimum, batas nilai persediaan, anggaran biaya penyelamatan.
2. **Jadwal, bukan cuma pemicu.** Pekerjaan yang terjadi karena jam berkata
   begitu, bukan karena ada yang rusak: pemeriksaan pemesanan harian,
   penilaian pemasok mingguan, paket rencana bulanan.
3. **Lingkaran tertutup.** Hasil nyata mengubah parameternya sendiri.
   Pengiriman yang telat menaikkan titik pesan ulang untuk pemasok itu.

Nomor tiga yang membuatnya agen, bukan skrip yang pintar. Sekarang
`record_outcome` sudah mencatat hasil, tapi **tidak ada satu pun yang
membacanya kembali untuk mengubah keputusan berikutnya.**

## Yang sudah ada dan dipakai ulang

Rencana ini tidak mulai dari nol:

- 12 agen, 33 alat, 12 instruksi tertulis
- Mesin hitung murni Python: proyeksi stok harian, pencocokan transfer,
  peramalan, audit
- Veto aturan dengan aritmatika, paket aturan 7 dokumen, 39 parameter
- Batas wewenang per peran, jejak persetujuan, pencatatan hasil
- Pemantau cuaca tiap 5 menit, pemindai risiko mingguan
- Label asal data di setiap angka, dan penolakan menjawab kalau data tak layak
- Jalur upload: data perusahaan sendiri mengalahkan sistem demo

## Fase 0 — Hentikan kebocoran (hari 1-3) — SELESAI

Semua di atasnya mewarisi kesalahan ini kalau tidak dibereskan dulu.

| Masalah | Perbaikan |
|---|---|
| Tiga lapis koreksi tanggal dibuang | `Ruling` membawa tanggal efektif; mesin memakai yang **paling lambat** di antara tanggal master, izin impor, tunggu pelabuhan, persetujuan sampel |
| Dokumen bilang tunggu 5 hari, kode pakai 4 | Kode membaca parameter dokumen, bukan angka tertanam |
| 4 agen masih di data contoh | Dara, Milo, Kira, Tara pindah ke jalur SAP/upload |
| Kira tak kenal opsi live | Kira mencari opsi di sumber yang sama dengan Clint |
| Opsi live tak punya tanggal & rupiah | Tanggal = tanggal pesan + lead time terukur; rupiah butuh kurs (di bawah) |
| Denda keterlambatan tak pernah dihitung | Bandingkan biaya penyelamatan melawan denda, supaya "tak ada yang aman" tetap punya jawaban |

**Soal kurs.** `ExtraCost` opsi live dalam mata uang dokumen, rupiahnya
sengaja kosong. Keputusannya: satu kurs di konfigurasi, berlabel, bersumber
kurs tengah Bank Indonesia dengan tanggalnya, ditulis di
`references/` seperti parameter lain. Kurs yang tidak disebut asalnya adalah
jenis angka yang sistem ini menolak.

**Bukti selesai:** opsi D direncanakan pada 9 Oktober, bukan 26 September.
Opsi live punya tanggal dan rupiah. Ada rekomendasi meski tak ada yang aman.

## Fase 1 — Sistem punya angkanya sendiri (hari 4-6) — SELESAI

Ini yang paling mengubah sifatnya. Berkas baru `engine/planning.py`, Python
murni, tanpa AI, seperti mesin hitung yang lain.

**Titik pesan ulang dan cadangan aman.** Sekarang batas aman 14 hari dipakai
untuk semua barang, dan `get_safety_stock_policy` selalu kosong. Diganti
hitungan sebenarnya:

```
cadangan aman   = z × akar( LT × sebaran_permintaan² + permintaan² × sebaran_LT² )
titik pesan ulang = permintaan_harian × LT + cadangan aman
```

Artinya sederhana: barang yang pemakaiannya naik-turun, atau pemasoknya suka
telat, butuh cadangan lebih banyak. Barang yang stabil tidak. `z` datang dari
target tingkat layanan, jadi targetnya yang menentukan cadangannya, bukan
angka 14 yang tidak ada asalnya.

**Kebutuhan bersih.** Stok ada + sedang jalan − permintaan − yang sudah
dijanjikan ke penanganan lain = berapa yang perlu dipesan, dan kapan.

**Dua bahan, dan hanya satu sudah ada.** Ini harus jujur:

| Bahan | Tersedia? |
|---|---|
| Sebaran lead time per pemasok | **Ada.** Dihitung dari sebaran banyak PO per pemasok, 597 PO live |
| Sebaran permintaan harian | **Belum.** `DailyConsumption` cuma satu angka tetap per material, tidak ada riwayat |

Jadi sebaran permintaan harus datang dari **upload riwayat pemakaian**
(material, tanggal, jumlah terpakai) yang memang ada di SAP sebagai pergerakan
material. Sampai itu diupload, angkanya adalah asumsi berlabel dengan tombol
yang kelihatan, bukan angka yang menyamar sebagai hasil hitungan.

**Bukti selesai:** `get_safety_stock_policy` mengembalikan angka beserta
alasannya. Daftar harian "12 material di bawah titik pesan ulang" muncul.

## Fase 2 — Janji ke pelanggan dan alokasi (hari 7-8) — SELESAI

Sisi pelanggan, yang sekarang kosong.

- **Bisa dijanjikan atau tidak.** Untuk satu permintaan pelanggan: bisa
  dipenuhi atau tidak, dan kalau tidak, tanggal paling awal yang bisa.
- **Alokasi saat kurang.** Pasokan tidak cukup untuk semua pesanan, lalu
  siapa yang dikorbankan? Urutkan berdasarkan denda per unit dan nilai
  pesanan, usulkan pembagiannya, hitung biaya tiap pilihan.

Data dendanya sudah ada di pesanan penjualan dan belum pernah dipakai.

**Bukti selesai:** satu kasus kekurangan menghasilkan usulan pembagian yang
menyebut pelanggan mana yang telat, berapa hari, berapa dendanya, dan kenapa
pelanggan itu yang dipilih.

## Fase 3 — Jalan sendiri menurut jam (hari 9-10) — SELESAI

Perluas `signals/watch.py` yang sudah jalan. Tidak ada infrastruktur baru.

| Jadwal | Isi | Wewenang |
|---|---|---|
| Harian | Periksa titik pesan ulang, usulkan pesanan | Di bawah batas: jalan sendiri. Di atas: minta persetujuan |
| Mingguan | Nilai pemasok, sertifikat mau habis, pemasok tunggal | Hanya melapor |
| Bulanan | Paket rencana: permintaan, pasokan, persediaan, risiko | Hanya melapor |

Setiap jadwal membuat kejadian dan run, jadi semuanya masuk ke jejak audit
yang sudah ada.

**Bukti selesai:** tinggalkan sistem menyala semalam, besok paginya ada
antrean usulan yang tidak dibuat siapa pun secara manual.

## Fase 4 — Belajar dari hasil (hari 11) — SELESAI

Fase paling kecil dan paling penting. Ini yang membedakan agen dari alat.

- Baca `actions.outcome` dan `outcome_at`, bandingkan janji dengan realisasi
- Perbarui lead time dan keandalan per pemasok
- Angka itu masuk kembali ke cadangan aman dan ke nilai pemasok

**Bukti selesai, dan ini momen demonya:** catat satu pengiriman telat, lalu
tunjukkan titik pesan ulang pemasok itu naik, dan nilainya turun. Sistem
mengubah keputusannya sendiri karena kenyataan, bukan karena orang mengedit
parameter.

## Fase 5 — Buktikan dengan angka (hari 12-14) — SELESAI

Yang dilihat juri.

- **Papan ukur:** ketepatan kirim, tingkat pemenuhan, hari cadangan, nilai
  persediaan, biaya penyelamatan, rasio keputusan sendiri vs dieskalasi
- **Tampilan yang datanya sudah ada tapi belum kelihatan:** tabel sumber
  alternatif dengan harga dan lead time nyata per pemasok, daftar 88 material
  bersumber tunggal, keterangan tetap soal asal data
- **Antrean harian** dari Fase 3

## Fase 6 — Pengerasan (hari 15-16)

- 13 kerentanan dependensi (1 kritis, 5 tinggi)
- **Putar dua kunci yang pernah masuk transkrip obrolan** — belum dilakukan
- Bersihkan: service worker basi di localhost, baris demo tersisa di DB,
  sisa template halaman masuk, "sepuluh spesialis" seharusnya sebelas
- Latihan demo dari awal sampai akhir

## Batas yang jujur

**Tulis balik ke SAP berhenti di usulan.** Dua sasaran tulis balik menjawab
403 karena tenant BTP lomba ini tidak punya ERP. Jadi lingkaran operasinya
lengkap sampai persetujuan dan pencatatan hasil, dan penulisan ke SAP
terbukti melawan sistem demo, bukan melawan ERP produksi. Ini harus
dikatakan di demo, bukan disembunyikan.

## Yang sengaja tidak dikerjakan

Dari 21 aplikasi AI di rantai pasok yang jadi acuan: pencurian kargo, muat
truk, otomasi gudang, sistem gudang, inspeksi visual, perawatan prediktif,
layanan pelanggan, retur, keberlanjutan, last-mile, keselamatan kerja.
Semuanya pekerjaan sistem lain. Menambahkannya dalam 16 hari berarti semuanya
dangkal.

## Kalau waktu habis, ini yang dipotong

Urutan potongnya: paket rencana bulanan, lalu lebar papan ukur (sisakan
ketepatan kirim saja), lalu alokasi.

**Yang tidak boleh dipotong: Fase 0 dan Fase 4.** Tanpa Fase 0 angka di layar
salah. Tanpa Fase 4 ini bukan agen.

## Yang bisa dikerjakan paralel oleh rekan tim

Fase 5 bagian tampilan tidak bergantung pada Fase 1-4 dan bisa jalan sejak
hari pertama: tabel sumber alternatif, daftar material bersumber tunggal,
keterangan asal data. Datanya sudah ada di API hari ini.
