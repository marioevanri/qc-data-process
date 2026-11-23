# Panduan qc-data-process

Catatan ini menjelaskan isi repo: tiap folder, tiap script, urutan menjalankannya, dan bagian mana yang perlu diubah kalau dipakai untuk data lain. Semua data di sini fiktif, pabriknya PT Sari Krimer Nusantara buatan generator.

## Gambaran besar

Repo ini punya tiga bagian yang berurutan.

| Folder | Isi | Hasilnya |
|---|---|---|
| `generator/` | pembuat data dan dokumen pabrik fiktif | file mentah per departemen di `generator/data/raw` dan sekitar 180 dokumen di `generator/docs` |
| `pipeline/` | pembersih data mentah | satu database SQLite, `db/qc.db` |
| `assistant/` | asisten QC berbasis chat | jawaban dari dokumen dan dari database |

Alurnya: generator membuat data kotor seperti di pabrik sungguhan, pipeline membersihkannya dan menyatukannya dalam satu database, lalu asisten menjawab pertanyaan dari dokumen dan database itu.

Folder `work/` berisi notebook profiling, yaitu catatan masalah yang ditemukan di tiap file mentah sebelum dibersihkan.

## Urutan menjalankan dari nol

Semua perintah dijalankan di Anaconda Prompt.

```
cd C:\projects\qc-data-process

rem 1. buat data dan dokumen (sekali saja, hasilnya tidak ikut ke GitHub)
cd generator
pip install -r requirements.txt
python generate.py
cd ..

rem 2. bersihkan data dan buat database
python pipeline\build_db.py
python pipeline\check_against_key.py

rem 3. jalankan asisten
cd assistant
pip install -r requirements.txt
python eval\run_data_eval.py
set GEMINI_API_KEY=isi-key-kamu
streamlit run app.py
```

API key jangan pernah ditulis di dalam file. Cukup lewat perintah `set` atau file `.streamlit\secrets.toml`, yang sudah dikecualikan dari git.

## Bagian 1: generator

Generator membuat pabrik fiktif dengan 3 line (P1, P2, RT), 5 grade, dan data Januari 2025 sampai Juni 2026.

| File | Fungsi |
|---|---|
| `config.py` | semua pengaturan: grade dan speknya, supplier, analis, dan seberapa kotor datanya (bagian `MESS`) |
| `generate.py` | script utama, menjalankan semuanya |
| `simulate.py`, `quality.py`, `outbound.py` | simulasi produksi, hasil uji, pengiriman, dan komplain |
| `mess.py` | mengotori data bersih jadi data mentah: typo, duplikat, koma desimal, format tanggal campur |
| `doc_sop.py` | isi SOP dan spesifikasi produk |
| `documents.py` | membuat NCR, memo, logbook, notulen, dan laporan investigasi |
| `events.py`, `formula.py`, `ANSWER_KEY.md` | kejadian tersembunyi di data. Ini kunci jawaban untuk project early warning, jangan dibuka sebelum project itu dikerjakan |

Hasil generator ada di tiga tempat:

- `generator/data/raw`: file mentah per departemen. Ini yang dibersihkan pipeline.
- `generator/data/clean`: versi bersih buatan generator. Dipakai sebagai kunci jawaban untuk menilai hasil cleaning.
- `generator/docs`: dokumen yang dibaca asisten.

Seed yang sama belum tentu menghasilkan data yang sama di komputer lain. Dengan seed 42, generator di laptop menghasilkan 182 dokumen, sedangkan di lingkungan cloud (Python 3.13, numpy 2.5) hasilnya 169 dokumen dengan nomor batch yang berbeda. Penyebabnya belum dicek, kemungkinan versi Python atau numpy. Pertanyaan uji di `assistant/eval` menyebut nomor komplain, batch, dan lot dari data di laptop, jadi kalau generator dijalankan ulang di tempat lain, pertanyaan itu harus disesuaikan.

## Bagian 2: pipeline

Pipeline mengubah file mentah jadi tabel bersih di satu database. Hal yang sering berubah antar pabrik atau antar periode (tabel mana yang dipakai, judul kolom, batas wajar, cara orang menulis nama) disimpan di file CSV di `pipeline/config`, terpisah dari kode. Kalau sumber datanya berubah, yang diedit cukup file config.

### `config/`, pengaturan tanpa mengubah kode

| File | Isi | Diubah kalau |
|---|---|---|
| `sumber_data.csv` | daftar tabel: aktif atau tidak, folder, pola nama file, pemilik data | ada sumber baru, sumber dimatikan, nama file berubah |
| `kolom.csv` | judul kolom di file mentah, nama bakunya, tipe, wajib atau tidak | kolom berganti nama, bertambah, atau hilang |
| `batas_wajar.csv` | rentang wajar per kolom, tindakan kalau di luar rentang, batas sensor macet | alat atau satuan berubah |
| `padanan_grade.csv` | penulisan grade dan kode bakunya | muncul penulisan grade baru |
| `padanan_analis.csv` | nama depan analis dan ID-nya | ada analis baru |
| `padanan_supplier.csv` | penulisan nama supplier dan ID-nya | supplier baru atau salah ketik baru |
| `padanan_bahan.csv` | awalan lot internal dan kode bahannya | bahan baku baru |
| `padanan_staf.csv` | nama depan staf QC incoming dan nama lengkapnya | ada staf baru |
| `batas_mikro.csv` | batas TPC, kapang khamir, dan coliform per grade, disalin dari dokumen SPEC | spek berubah |
| `padanan_customer.csv` | penulisan nama customer dan ID-nya | customer baru atau singkatan baru |
| `padanan_status.csv` | penulisan status release dan status bakunya | muncul istilah status baru |
| `kategori_komplain.csv` | kata kunci keluhan dan kategori komplainnya, dicek berurutan dari atas | kategori baru, atau keluhan yang masuk kategori salah |
| `spek_produk.csv` | spek per grade, parameter, dan revisi, salinan DCIS dari RND | RND menerbitkan revisi spek |
| `padanan_parameter.csv` | nama parameter di spek dan kolom database tempat hasilnya | parameter baru di spek |

Di file padanan, penulisan dicocokkan setelah diubah ke huruf kecil dan dibuang spasi serta tanda bacanya. `NDC 28P` dan `ndc-28p` cukup ditulis satu baris, `ndc28p`. Untuk supplier dan customer, kata PT dan CV juga dibuang.

**`sumber_data.csv`.** Kolom `aktif` diisi `ya` atau `tidak`. Tabel yang `tidak`, atau filenya tidak ketemu, dilewati saat membuat database, dan tabel lamanya dihapus dari database supaya tidak tertinggal data basi. Kolom `pemilik` hanya catatan departemen yang memberi data.

**`kolom.csv`.** Satu baris per kolom di file mentah.

| Kolom | Isi |
|---|---|
| `kolom_raw` | judul kolom persis seperti di file |
| `kolom_baku` | nama di database. Dua judul boleh diarahkan ke satu nama, misalnya `Visko (cP)` dan `Viskositas (cP)` karena lembar lab berganti judul di 2026 |
| `tipe` | `angka`, `tanggal`, `waktu` (tanggal plus jam), `jam`, `grade`, `batch`, atau `teks` |
| `wajib` | `ya` kalau tabel tidak bisa dibersihkan tanpa kolom ini |

Kolom di file yang tidak terdaftar dibuang. Kolom terdaftar yang tidak ada di file diisi kosong, lalu disebut di keluaran build_db sebagai "kolom tidak ada di file". Kalau yang hilang kolom wajib, build berhenti dan menyebut nama kolomnya. Jadi kalau Produksi hanya memberi sebagian kolom, misalnya tanpa tekanan homogenizer, kodenya tidak perlu disentuh selama kolom itu tidak wajib.

Kolom `tipe` hanya dipakai `clean_generic`, yaitu pembersih untuk tabel yang tidak punya script sendiri. Tabel yang punya script memakai `kolom_raw`, `kolom_baku`, dan `wajib`, sedangkan aturan lainnya ada di script masing-masing.

**`batas_wajar.csv`.** `min` dan `maks` boleh diisi salah satu. `jika_di_luar` berisi `bagi 10` untuk salah koma (1827.3 yang seharusnya 182.73) atau `kosongkan` untuk kode sensor seperti 0 dan 9999. `maks_sama_berturut` hanya dipakai logger dryer: nilai yang sama lebih dari sekian kali berturut-turut dianggap sensor macet dan dikosongkan.

**Formula dari RND.** Baris `formula` sudah ada di `sumber_data.csv` dan `kolom.csv` dengan `aktif` = `tidak`, karena belum ada datanya. Kalau RND memberi file:

1. Taruh filenya di `generator/data/raw/formula/`, atau ubah `folder` dan `pola_file` di `sumber_data.csv`.
2. Sesuaikan baris `formula` di `kolom.csv` dengan judul kolom di file itu.
3. Ubah `aktif` jadi `ya`.

Tabel ini dibersihkan `clean_generic`, jadi tidak perlu script baru selama isinya rapi. Kalau ternyata butuh aturan khusus, baru dibuat `clean_formula.py` dan didaftarkan di `CLEANERS` di `build_db.py`. Cara yang sama berlaku untuk tabel baru lain.

### `common.py`, alat bantu bersama

Fungsi kecil yang dipakai semua script cleaning.

| Fungsi | Yang dikerjakan | Contoh |
|---|---|---|
| `read_source` | membaca semua file satu tabel sesuai `sumber_data.csv`, mengganti judul kolom sesuai `kolom.csv`, menambah kolom `source_file` | `KimFis_*.csv` di folder `qc_lab` |
| `read_raw` | membaca satu file sebagai teks. CSV dideteksi pemisahnya, Excel dibaca langsung | file dari Excel berbahasa Indonesia memakai `;` |
| `drop_exact_duplicates` | membuang baris yang persis sama, nama file tidak ikut dibandingkan | baris yang terekspor dua kali |
| `parse_date` | membaca tanggal dari beberapa format sekaligus, termasuk angka seri Excel | `02/01/2025`, `2025-01-02`, `02-Jan-25`, `45659` |
| `clean_grade` | menyeragamkan nama grade lewat `padanan_grade.csv` | `NDC 28P`, `ndc-28p`, `Krimer 35` |
| `clean_batch` | membuang garis miring, spasi, dan tanda hubung. Huruf O dan I di 8 karakter pertama diganti 0 dan 1 | `250102/61/RT` dan `25O10261RT` jadi `25010261RT` |
| `repair_batch` | batch yang tidak ada di log produksi dicari ulang lewat tanggal, grade, dan line. Tanpa log produksi, hanya penulisannya yang dirapikan | `25101431P1` yang tertulis untuk `25011431P1` |
| `nearest_batch` | untuk lembar tanpa tanggal produksi (pengiriman, release, verifikator). Batch yang tidak ada di log produksi, atau dibuat di luar rentang hari yang masuk akal, dicocokkan ke batch grade sama dengan salah ketik paling sedikit | `20512031P1` jadi `25012031P1`. `25013147P2` di DO bulan November jadi `25103147P2` |
| `typo_distance` | jumlah salah ketik antara dua nomor. Dua angka bersebelahan yang tertukar dihitung satu | `250861` dan `250816` berjarak 1 |
| `squash` | nama yang diketik bebas jadi huruf kecil tanpa PT, CV, spasi, dan tanda baca | `PT. KIS` jadi `kis` |
| `date_from_batch` | tanggal produksi dari nomor batch | `25010231P1` jadi 2 Januari 2025 |
| `mix_start_of` | jam mulai mix sebuah sampel, dari batch dan huruf pertama kode sampel | sampel `B2` milik mix B |
| `production_day` | hari produksi dari tanggal dan jam. Hari produksi berjalan 07.00 sampai 07.00 | jam 02.00 tanggal 3 masih hari produksi tanggal 2 |
| `clean_sample_code` | menyeragamkan kode sampel | `c1`, `B 2`, `B-2`, `2A` |
| `clean_lot` | merapikan nomor lot bahan baku | `po-250103-1` jadi `PO-250103-01` |
| `clean_analyst` | nama analis dan verifikator jadi ID | `Andi`, `ANDI`, `Andi P.` jadi `AN01`, `Hendra G.` jadi `VR01` |
| `clean_time` | menyamakan penulisan jam | `10.31` jadi `10:31` |
| `to_number` | teks jadi angka, menerima koma desimal | `2,66` jadi 2.66, `ND` jadi kosong |
| `apply_limits` | menjalankan `batas_wajar.csv` untuk satu tabel | suhu inlet `1827.3` jadi 182.73 |
| `fix_decimal_shift_by_group` | membagi 10 nilai di atas 4 kali median grade-nya | protein 2 % di krimer dan 20 % di susu |
| `clean_generic` | membersihkan tabel hanya dari `tipe` di `kolom.csv` | log kontrol sensory, formula |
| `load_spec_limits` | spek per grade, parameter, dan revisi dari `spek_produk.csv`, beserta kolom tempat hasilnya | dipakai `clean_lab.py` untuk `retest_of` dan `build_db.py` untuk tabel `spec_limits` |

Semua data dibaca sebagai teks dulu, baru diubah ke angka atau tanggal satu kolom demi satu kolom. Kalau langsung dibaca sebagai angka, nilai seperti `2,66` atau `?` membuat pandas menebak sendiri dan kesalahannya tidak kelihatan.

`RAW_DIR` dan `DOC_DIR` di bagian atas file menunjuk folder data mentah dan folder dokumen.

`SourceOff` adalah tanda bahwa sebuah tabel dimatikan atau filenya tidak ada. Script yang menerima tanda ini melewati tabelnya tanpa membuat build gagal.

### `clean_production.py`, log produksi

Satu baris per mix. Tabel ini dikerjakan pertama karena kuncinya (`batch_no` dan `mix_id`) dipakai untuk memperbaiki dan menyambungkan tabel lain.

1. Buang baris duplikat.
2. Seragamkan line, grade, batch, dan nomor lot.
3. Susun jam mulai dan selesai. Mix jam 02.00 masih milik hari produksi sebelumnya.
4. Tentukan huruf mix. Kolom Mix No di log produksi menghitung mix per line per hari, sedangkan lab dan sensory memakai huruf yang menghitung mix per nomor batch. Jadi huruf ditentukan dari urutan jam mulai di dalam satu batch, yang pertama A.
5. Ubah kolom angka dan perbaiki salah koma lewat `batas_wajar.csv`.

`production_or_none()` dipakai script lain untuk mengambil log produksi. Kalau log produksi dimatikan, fungsi ini mengembalikan `None` dan script lain beralih ke aturan cadangan.

### Kalau log produksi tidak ada

Lab, sensory, mikro, dan NIRS memakai log produksi untuk dua hal: memperbaiki nomor batch yang salah ketik, dan menentukan tanggal kalender sampel malam dari jam mulai mix-nya. Tanpa log produksi, script tetap jalan dengan aturan cadangan. Batch hanya dirapikan penulisannya, dan jam sebelum 07.00 dianggap milik hari produksi sebelumnya.

Hasil uji coba dengan `production_mix_log` dimatikan, dibandingkan dengan hasil normal:

| Tabel | Yang jadi salah |
|---|---|
| lab | 57 sampel batch-nya tidak bisa diperbaiki, 182 jam sampling dan jam uji salah hari |
| sensory | 79 sampel batch-nya tidak bisa diperbaiki, 1.356 jam uji salah hari |
| mikro | 2 batch tidak bisa diperbaiki |
| NIRS | 44 sampel tanpa tanggal masuk ke batch yang salah, 51 kontrol salah tanggal |

Pengiriman, release, dan verifikator juga memakai log produksi untuk memperbaiki batch lewat `nearest_batch`. Tanpa log produksi, batch di tabel itu hanya dirapikan penulisannya. Dampaknya belum diukur. Sampel transisi retail tanpa log produksi tetap dapat nomor transisi dan urutan sampel, tapi batch dan mix-nya kosong.

Lebih dari 99 % baris tetap benar, jadi tabel QC masih bisa dipakai. Yang paling terganggu adalah analisis per jam, misalnya mengaitkan hasil sensory dengan pembacaan dryer. Kalau Produksi hanya mau memberi sedikit, minta lima kolom wajibnya saja: tanggal, line, produk, batch, dan jam mulai.

### `clean_lab.py`, hasil uji KimFis

Satu baris per pengujian sampel, dari 19 file bulanan.

1. Gabung semua file. Judul kolom yang berubah di Januari 2026 sudah disatukan lewat `kolom.csv`.
2. Perbaiki identitas sampel: grade, batch, kode sampel, analis. Batch yang salah ketik diperbaiki dengan `repair_batch`. Tanggal produksi dibaca dari nomor batch, karena untuk sampel lewat tengah malam sebagian analis menulis tanggal kalender.
3. Susun jam sampling dan jam uji. Jam sampling dibandingkan dengan jam mulai mix-nya, supaya sampel terakhir mix malam yang diambil sesudah 07.00 tetap jatuh di hari yang benar.
4. Ubah angka. Bulk density yang ditulis dalam g/L dibagi 1000, salah koma dibagi 10.
5. Buang entri yang diketik dua kali untuk sampel dan jam uji yang sama. Yang disimpan entri pertama.
6. Tandai retest, yaitu sampel yang sama diuji lagi di jam yang berbeda.
7. Isi `retest_of`, parameter yang memicu retest. Lembar lab tidak menulisnya, jadi dicari dari uji sebelumnya: parameter yang di luar spek, menurut revisi spek yang berlaku di tanggal produksi. Kalau nilai di uji sebelumnya kosong atau tidak terbaca, dipakai hasil retest itu sendiri, karena retest yang masih di luar spek menunjukkan untuk apa retest itu dijalankan. Dari 103 retest, 100 terisi dan semuanya cocok dengan kunci jawaban. Tiga sisanya kosong: satu karena nilai lemaknya tidak ada di uji mana pun, dan dua lagi baris yang ditandai retest padahal tidak ada di kunci (kemungkinan kode sampel tertukar, lihat penjelasan di bawah).

Semua pengujian tetap tersimpan di `qc_lab_kimfis`. Hasil yang dipakai adalah hasil terakhir, dan itu disusun di tabel kedua, `qc_lab_final`: satu baris per sampel, tiap parameter diisi nilai terakhir yang terukur, plus `n_tests` (jumlah pengujian). Per parameter, bukan per baris, karena retest tidak selalu mengulang semua parameter. Contohnya `25010947P2-C2`: kadar air dan viskositas diambil dari retest, tapi lemak dan protein hanya diukur di uji pertama, jadi nilainya diambil dari sana. Kalau hanya baris terakhir yang dipakai, lemaknya hilang.

Aturannya: untuk tiap parameter, mundur dari uji paling akhir sampai ketemu nilai yang terisi. Kalau fat diuji 3 kali dengan hasil 30,5, lalu 30,4, lalu kosong, yang dipakai 30,4 dari uji ke-2. Risikonya, sel yang kosong karena tidak diuji tidak bisa dibedakan dari sel yang kosong atau tidak terbaca karena salah catat. Di data asli, hitung baris retest yang semua kolom angkanya kosong. Kalau banyak, berarti hasil retest dicatat di tempat lain.

### `clean_sensory.py`, hasil sensory KimFis

Satu baris per sampel yang dicicipi, dari 19 file bulanan. Lembar ini berubah di Januari 2026 mengikuti SOP-QC-005 Rev 03: skala kata jadi angka, ada kolom ID kontrol, dan kolom "Hasil" jadi "Grade Sensory". Satu file punya dua kolom hasil sekaligus.

1. Gabung semua file, buang baris duplikat.
2. Perbaiki identitas sampel dengan aturan yang sama seperti lab. Bedanya, tanggal di lembar sensory selalu tanggal produksi, jadi batch yang tanggalnya tidak cocok dengan kolom tanggal juga diperbaiki (`date_must_match=True`).
3. Susun jam uji. Sampel tidak mungkin dicicipi sebelum mix-nya mulai, sama seperti jam sampling di lab.
4. Ubah skor ke satu skala -2 sampai +2. Semua penulisan ada di `SCALE`: `pass`, `0`, `sesuai`, `OK` jadi 0, `agak lebih`, `AL`, `1+` jadi +1, dan seterusnya. Skor yang kosong diisi dari catatan, karena analis menulis atribut yang menyimpang di sana ("creamy agak kurang"). Atribut yang tidak disebut di catatan dianggap 0.
5. Seragamkan hasil (`PASS`, `P`, `TP1 +`, `TP1(+)`, `tp3`), tandai off-flavor (TP3), dan tentukan jenisnya dari kata di catatan: tengik atau oily jadi `oxid`, campur grade atau transisi jadi `mixgrade`, gosong jadi `burnt`, sisanya `random`. Kata yang salah ketik seperti "tenggik", atau yang menempel tanpa spasi seperti "aromatengik", tetap dikenali.
6. Isi ID kontrol. Lembar 2025 tidak punya kolom kontrol, jadi kontrol dicari di tabel `sensory_controls` menurut grade dan tanggal produksi. Tanggal produksi yang dipakai, bukan tanggal uji, karena sampel malam yang dicicipi lewat tengah malam tetap memakai kontrol hari produksinya. Kalau log kontrol dimatikan, ID kontrol diisi apa adanya dari lembar.

Script ini juga mengecek apakah hasil cocok dengan skornya menurut SOP-QC-005 bagian 7. Di data ini semuanya cocok.

Jam sampling sengaja tidak disalin ke tabel sensory. Kalau perlu, ambil dari tabel lab lewat `sample_uid`.

### `clean_controls.py`, log kontrol sensory

`Log_Kontrol_Sensory.csv` sudah rapi, jadi dibersihkan `clean_generic` dan jadi tabel `sensory_controls`. Tabel ini dipakai sensory dan NIRS untuk mengisi ID kontrol.

Script ini hanya menambah satu kolom, `extended`: kontrol dipakai melewati tanggal jatuh temponya (`end_use` lebih lambat dari `due_date`). Ada 9 kontrol seperti itu, semuanya dengan catatan bahwa kontrol baru belum siap atau belum tersedia. Lima kontrol terakhir belum punya tanggal ganti karena masih dipakai saat data berakhir. Untuk lima kontrol ini `extended` dibiarkan kosong, karena belum diketahui apakah nanti diperpanjang.

### `clean_micro.py`, hasil mikrobiologi

Satu baris per batch, dari 2 file tahunan.

1. Gabung, buang duplikat.
2. Perbaiki batch. Lembar mikro tidak punya tanggal produksi, jadi yang dipakai untuk mencari ulang batch adalah tanggal terima dikurangi satu hari.
3. Baca angka TPC. Lab menulisnya dalam beberapa bentuk: `610`, `1,3 x 10^2`, dan `1.8E+0`. Bentuk terakhir adalah tampilan Excel yang terpotong dari `1.8E+03`, pangkatnya hilang, jadi nilainya tidak bisa diketahui (bisa 18, 180, atau 1800). Nilai seperti ini dibiarkan kosong.
4. Coliform dan kapang khamir yang ditulis `<10` disimpan sebagai kosong dengan penanda `coliform_lt10` atau `ym_lt10`. Angka pastinya memang tidak diukur lab.
5. Status `MS` dan `TMS` diubah jadi Pass dan Fail. Alasan TMS ditulis ulang dari batas di `batas_mikro.csv`, lalu dicocokkan dengan status dari lab.

### `clean_rm.py`, penerimaan bahan baku (QC incoming)

Satu baris per kedatangan bahan baku, dari 3 file tahunan (2024 sampai 2026). Kuncinya nomor lot internal. Nomor penerimaan yang ada di kunci jawaban tidak tercatat di lembar, jadi tidak dibuat.

1. Buang duplikat.
2. Baca tanggal terima. Satu kolom berisi tiga format tanggal dan sebagian angka seri Excel (45649 adalah 23 Desember 2024). Tanggal lalu digabung dengan jam terima.
3. Kode dan nama bahan yang kosong diisi dari awalan lot internal lewat `padanan_bahan.csv`. Lot `HCO-...` selalu Hydrogenated Coconut Oil.
4. Cocokkan nama supplier yang diketik bebas (`PT. Gula Pati Nusantara`, `gulapati`, `GPN`) lewat `padanan_supplier.csv`. Penulisan yang tidak dikenal dihitung di catatan `supplier_tidak_dikenal`, tinggal ditambahkan ke file padanan.
5. Ubah jumlah dalam ton (dengan koma desimal) ke kg.
6. Ubah hasil uji COA dan QC jadi angka. Isian `-` dan `lihat COA` jadi kosong.
7. Seragamkan keputusan jadi Accept, Conditional, atau Reject (`terima`, `OK bersyarat`, `ditolak`, dan seterusnya), dan nama inspektur jadi nama lengkap lewat `padanan_staf.csv`.

### `clean_nirs.py`, hasil NIRS

Satu baris per scan, dari 2 file tahunan. Isinya prediksi kadar air, lemak, dan protein dari model kalibrasi NIRS. Semua scan disimpan, kolom `scan_type` membedakan sampel produksi (`sample`), kontrol (`control`), dan sisanya (`other`).

1. Tandai scan ulang, yaitu nomor scan berakhiran R yang nomor aslinya ada (964 scan). Perlakuannya seperti retest di lab: dua-duanya disimpan, scan ulang diberi `is_rescan` = 1 dan `rescan_of` berisi nomor scan pertamanya. Scan ulang selalu 2 menit sesudah scan pertama dan selisih hasilnya rata-rata 0,06 poin, jadi ini gambaran repeatability alat. Identitas sampelnya (batch, tanggal, line, kontrol) disalin dari scan pertama. Yang dipakai adalah scan terakhir, ditandai `is_latest` = 1. Scan ulang NIRS selalu berisi ketiga prediksi, jadi cukup ditandai per baris, tidak perlu tabel kedua seperti lab.
2. Baca grade dari nama model kalibrasi: `NDC28P_v2` jadi NDC-28P.
3. Pecah nama sampel. Analis mengetiknya bebas di software NIRS: `25010247P2 A1`, `A1-25010231P1`, `25010231P1B3`, `A2 31P1`, `CTRL-31-001`, `kontrol 61`. Scan yang bukan sampel produksi atau kontrol (120 scan) disimpan sebagai `other`: cek alat (`test`, `xx`, `cek alat`), `sampel kompetitor`, dan `trial RND`. Grade-nya dikosongkan, karena model yang dipakai saat scan tidak menjelaskan sampelnya. Model kalibrasi tetap tercatat di kolom `product_model`.
4. Cari batch untuk nama tanpa tanggal seperti `B3 31P1`. Kandidatnya hari produksi saat scan dan sehari sebelumnya. Yang dipilih batch yang mix B-nya sudah mulai paling akhir sebelum jam scan. Ini perlu karena sampel malam sering baru di-scan sesudah jam 07.00.
5. Tentukan tanggal dan line kontrol. Kontrol tidak punya batch, tapi selalu di-scan tepat sebelum sampel pertama sebuah run (satu grade di satu line pada satu hari produksi), kadang lewat tengah malam untuk run malam. Jadi tanggal dan line-nya diambil dari run berikutnya. Kontrol yang ditulis tanpa ID (`kontrol 34`, `CTRL NDC-28P`) dicari ID-nya di `sensory_controls`.
6. Kalau satu grade jalan di dua line pada hari yang sama dan kedua kontrolnya di-scan sebelum run mana pun mulai, tidak ada petunjuk kontrol mana untuk line mana. Line-nya dibiarkan kosong (224 scan), tanggalnya tetap terisi. Kalau ditebak dari urutan scan, benarnya cuma 67 %.

Karena semua scan disimpan, query untuk hasil produksi perlu menyaring `scan_type = 'sample' AND is_latest = 1`. Tanpa saringan itu, rata-rata per grade ikut tercampur scan cek alat dan sampel kompetitor, dan sampel yang di-scan ulang terhitung dua kali.

File spektrum `NIRS_Spectra_*.csv.gz` belum dimasukkan ke database.

### `clean_logger.py`, logger spray dryer

Satu baris per pembacaan sensor tiap 30 menit, dari 57 file bulanan (3 line kali 19 bulan). Line hanya tertulis di nama file, misalnya `Dryer_P1_2025-01.csv`.

1. Buang baris yang persis sama (72).
2. Kosongkan nilai di luar rentang `batas_wajar.csv`. Angka 0 dan 9999 ditulis logger kalau sensornya putus.
3. Pembacaan dengan jam yang sama (121, kebanyakan jam 07.00 dan 07.30 saat ganti shift) disimpan dua-duanya, mengikuti kunci jawaban.
4. Kosongkan pembacaan sensor macet, yaitu nilai yang sama lebih dari 16 kali berturut-turut (8 jam). Di data ini kejadiannya 20 sampai 35 pembacaan. Batas 16 dipilih karena tekanan homogenizer tahap 2 ditulis bilangan bulat dan secara wajar bisa sama sampai 14 kali berturut-turut. Di data asli, cek dulu berapa lama nilai tiap sensor bisa wajar tidak berubah sebelum memakai angka ini.

Ada 212 pembacaan di kunci jawaban yang tidak ada di file mentah. Kira-kira enam kali logger mati di ketiga line, masing-masing 12 sampai 22 jam. Tabel bersih memang berlubang di jam-jam itu dan tidak bisa diisi.

### `clean_verifikator.py`, verifikasi sensory H+1

Satu baris per sampel yang dicicipi ulang verifikator, dari `Verifikasi_H1.csv`.

1. Buang baris yang persis sama (94).
2. Perbaiki batch. Verifikator mencicipi 1 atau 2 hari setelah produksi, jadi batch yang dibuat di luar rentang itu dianggap salah ketik dan dicocokkan lewat `nearest_batch` (60 batch).
3. Nama verifikator jadi ID lewat `padanan_analis.csv`: `Hendra G.`, `HENDRA`, dan `VR01` jadi VR01.
4. Skor, hasil, dan jenis off-flavor diseragamkan dengan aturan yang sama seperti sensory KimFis (`SCALE`, `clean_result`, `off_flavor_type`).
5. Kolom "Hasil KimFis" yang disalin verifikator dibiarkan apa adanya, 1.306 di antaranya kosong. Query mengambil hasil KimFis langsung dari `sensory_kimfis` lewat `sample_uid`, bukan dari salinan ini.

Lembar ini hanya mencatat tanggal uji tanpa jam, jadi kolomnya `test_date`.

### `clean_release.py`, riwayat status release

Satu baris per perubahan status satu mix, dari `Status_Release.csv`.

1. Status diseragamkan lewat `padanan_status.csv`: `Karantina`, `QRT`, `RLS`, `Rilis darurat`, `Tahan`, `Tolak`, dan seterusnya.
2. Perbaiki batch lewat `nearest_batch`, dengan rentang dihitung dalam hari produksi (jam 02.30 masih hari sebelumnya). QUARANTINE dipasang sistem tepat setelah pengemasan, jadi batchnya dibuat paling lama 2 hari sebelumnya. Keputusan sesudahnya paling lama 30 hari.
3. Kolom Mix ditulis tiga cara. `C` berarti mix C. `E-G` berarti mix E dan G diputuskan bersamaan, bukan E sampai G. `ALL` berarti sisa mix batch itu yang masih menunggu (QUARANTINE atau HOLD) saat itu dan tidak mendapat keputusan di baris lain. Tiap mix jadi satu baris.

Kalau satu batch punya dua baris ALL, baris pertama mengambil semua mix yang menunggu, karena lembar tidak menyebut pembagiannya. Ini terjadi di 2 batch. Baris ALL kedua disimpan dengan `mix_id` berakhiran `-ALL`.

### `clean_shipments.py`, pengiriman

Satu baris per DO, dari 2 file tahunan.

1. Nama customer diketik bebas (`PT. KIS`, `Kopi Instan Sejahtera`, `MSA`, `CV KKR`) dan dicocokkan lewat `padanan_customer.csv`.
2. Grade diseragamkan, termasuk `NDC 28 Palm` dan `Susu Retail`.
3. Perbaiki batch lewat `nearest_batch`. Barang jadi di sini dikirim paling lama 17 hari setelah produksi, jadi batch yang dibuat lebih dari 30 hari sebelum tanggal kirim dianggap salah ketik.
4. Daftar mix ditulis `A,B,C`, jumlah jadi angka.

### `clean_complaints.py`, komplain customer

Satu baris per komplain, ditelusuri sampai batch dan DO.

1. Customer dicocokkan lewat `padanan_customer.csv`. Kategori diambil dari kata di keluhan lewat `kategori_komplain.csv`, dan urutan barisnya penting: "gumpalan putih mengapung di permukaan kopi" masuk feathering, bukan caking, karena "mengapung" dicek sebelum "gumpal".
2. Hasil investigasi jadi `justified`: Terbukti 1, Tidak terbukti 0. Komplain yang masih Open dibiarkan kosong karena belum diputuskan. Kunci jawaban generator mengisinya 0, jadi di penilai muncul 1 kosong.
3. Telusur batch dan DO, berurutan:
   - Laporan investigasi di `generator/docs/complaints`, baris "Batch ... (DO ...)". Ini hasil telusur QA, jadi didahulukan.
   - Kalau belum ada laporan, lot yang ditulis customer (`Lot: 25010862RT`, `LOT 25050331P1`, `25081861rt`, `26O20462RT`) dicocokkan ke batch yang pernah dikirim ke customer itu sebelum tanggal komplain: persis sama, awalannya sama (`25122034` tanpa line), lalu salah ketik paling sedikit.
   - Tulisan seperti "kiriman tgl 10/05" tidak dipakai. Dicek ke kunci jawaban, tanggal dari customer meleset 6 sampai 20 hari dari pengiriman sebenarnya, jadi hasilnya lebih sering salah.

Kolom `trace_source` mencatat dari mana batch didapat. Kalau laporan dan lot customer sama-sama ada tapi beda, jumlahnya dicatat di `lot_beda_dengan_laporan`.

### `clean_transition.py`, sampel transisi grade retail

Satu baris per sampel yang diambil saat line RT ganti grade, dari `Transisi_Retail.csv`, jadi tabel `retail_transition_samples`. Lembarnya cuma berisi tanggal, dari grade apa, ke grade apa, jam sampel, hasil, analis, dan keterangan. Nomor transisi, urutan sampel, batch, dan mix tidak ditulis, jadi disusun ulang.

1. Waktu sampel. Tanggal di lembar ini tanggal kalender, jadi sampel jam 01.30 masuk hari produksi sebelumnya (`production_day`).
2. Grade diseragamkan lewat `padanan_grade.csv` yang sudah ada (`Krimer Sachet` jadi CRM-RT, `Susu Retail` jadi MLK-RT). Hasil diseragamkan: `OK` jadi Pass, sedangkan `NG`, `campur`, dan `blm pass` jadi Belum Pass. Analis jadi ID lewat `padanan_analis.csv`.
3. Nomor transisi. Sampel dari satu kali ganti grade jaraknya paling lama beberapa menit, sedangkan dua kali ganti grade di line yang sama berjarak berjam-jam. Jadi jeda lebih dari 30 menit (`NEW_TRANSITION_GAP`) berarti transisi baru. Di data ini satu transisi paling panjang 7,7 menit dan jarak antar transisi paling pendek 208 menit, jadi batas 30 menit aman.
4. Mix yang disampling adalah mix pertama grade baru di line RT, yaitu mix terakhir yang mulai sebelum sampel pertama, paling lama 30 menit sebelumnya (`MIX_WINDOW`). Tanpa log produksi, batch dan mix dibiarkan kosong.
5. Dua kolom tambahan untuk analisis menit aman: `minutes_after_first` (menit sejak sampel pertama transisi itu) dan `minutes_after_mix_start` (menit sejak mix grade baru mulai, hanya kalau ada log produksi).

Hasilnya 424 transisi, semua cocok dengan kunci jawaban.

Dua hal yang perlu dicek sebelum dipakai di data asli:

- **Batas 30 menit.** Batas ini aman karena di sini dua kali ganti grade selalu berjauhan. Kalau di line asli ada mix yang pendek sehingga dua kali ganti grade terjadi dalam 30 menit, dua transisi itu akan tergabung jadi satu. Cek dulu sebaran jarak antar sampel di data asli.
- **Menit dihitung dari apa.** Di pabrik tidak ada jam resmi mulai transisi, yang tercatat cuma jam sampel. `minutes_after_first` dihitung dari sampel pertama, padahal sampel pertama sendiri diambil entah berapa menit setelah produk benar-benar berganti. Jadi "menit ke-4" di kolom ini belum tentu 4 menit setelah ganti grade. `minutes_after_mix_start` lebih dekat ke waktu ganti yang sebenarnya, tapi hanya sebaik jam mulai di log produksi. Jam itu juga belum tentu sama dengan saat produk baru sampai di titik sampling, karena masih ada produk lama di pipa dan dryer.

### Spek produk

`build_db.py` juga menulis tabel `spec_limits` dari `config/spek_produk.csv` dan `config/padanan_parameter.csv`: batas min, maks, atau syarat per grade, parameter, dan revisi, ditambah tabel dan kolom tempat hasilnya disimpan. File spek ini salinan DCIS yang sama dengan di COA Checker. Kalau RND menerbitkan revisi baru, tambahkan barisnya dengan `revisi` dan `berlaku_mulai` yang baru. Baris lama jangan dihapus, karena batch lama tetap dinilai dengan revisi yang berlaku saat diproduksi.

### `build_db.py`, pembuat database

Menjalankan cleaning untuk tiap tabel di `sumber_data.csv` dan menulis hasilnya ke `db/qc.db`. Log produksi dijalankan pertama, lalu hasilnya diberikan ke script lain. Tabel yang punya aturan khusus terdaftar di `CLEANERS`, sisanya dibersihkan `clean_generic`. Tabel turunan, yang dibuat dari tabel bersih dan disimpan di sebelahnya, terdaftar di `DERIVED`. Sekarang isinya satu, `qc_lab_final`. Terakhir, tabel `spec_limits` ditulis dari file spek.

Di keluarannya, tiap tabel menampilkan jumlah baris mentah dan bersih, atau alasan dilewati (dimatikan, atau file tidak ada).

File database tidak ikut ke GitHub. Siapa pun bisa membuatnya ulang dengan perintah yang sama.

### `check_against_key.py`, penilai hasil cleaning

Membandingkan tiap tabel di database dengan kunci jawaban generator, kolom per kolom. Keluarannya tiga angka per kolom:

- **cocok**: sama dengan kunci, dalam toleransi pembulatan.
- **beda**: ada nilainya tapi tidak sama dengan kunci. Ini yang harus diselidiki.
- **kosong**: di kunci ada nilainya, di hasil cleaning kosong. Biasanya karena di data mentah memang kosong atau berisi teks.

Tabel yang tidak ada di database (karena dimatikan) dilewati. Kunci yang muncul dua kali, seperti dua pembacaan logger di jam yang sama, dipasangkan berurutan: yang pertama dengan yang pertama.

Hasil saat ini:

| Tabel | Baris mentah | Baris bersih | Kolom yang beda |
|---|---|---|---|
| `production_mix_log` | 10.036 | 9.942 | tidak ada |
| `qc_lab_kimfis` | 30.500 | 29.927 | kadar air 21, viskositas 22, Brix 19 |
| `qc_lab_final` | | 29.824 | tidak dinilai, tidak ada di kunci |
| `sensory_kimfis` | 30.206 | 29.826 | 5 skor di 4 sampel |
| `sensory_controls` | 69 | 69 | tidak ada |
| `micro_results` | 2.190 | 2.166 | 2 alasan TMS |
| `rm_receiving` | 1.164 | 1.147 | tidak ada |
| `nirs_results` | 33.076 | 33.076 | tidak ada |
| `dryer_logger` | 54.026 | 53.954 | tidak ada |
| `sensory_verifikator` | 8.506 | 8.412 | tidak ada |
| `release_history` | 20.553 | 20.636 | alasan dan pemutus 4, di 2 batch dengan dua baris ALL |
| `shipments` | 2.328 | 2.328 | tidak ada |
| `complaints` | 37 | 37 | tidak ada |
| `retail_transition_samples` | 1.723 | 1.723 | tidak ada |

Penjelasan yang beda dan kosong:

- **Lab:** sekitar 20 pasang sampel yang kodenya tertukar saat diketik. Tidak bisa diperbaiki dari datanya sendiri.
- **Sensory:** 4 sampel TP3 yang skornya kosong dan catatannya hanya menyebut off-flavor, jadi skor atributnya tidak bisa diketahui.
- **Mikro, TPC kosong 236:** tampilan Excel terpotong (`1.8E+0`).
- **Mikro, coliform dan kapang khamir kosong:** hasil `<10`. Kunci jawaban generator menyimpan angka sebenarnya, lab tidak pernah mengukurnya.
- **Mikro, alasan TMS beda 2:** satu karena TPC-nya terpotong, satu karena TPC dibulatkan lab (`1,0 x 10^4` untuk 10.330).
- **Bahan baku, hasil COA kosong 7 sampai 61:** di lembar tertulis `-` atau `lihat COA`.
- **NIRS, hasil 33.076 baris sedangkan kunci 31.992:** kunci jawaban hanya memuat scan pertama sampel dan kontrol. Scan ulang dan scan `other` tidak ada di kunci, jadi tidak dinilai.
- **NIRS, line kosong 224:** kontrol yang line-nya tidak bisa dipastikan (langkah 6 di atas).
- **Logger, kosong 100 sampai 150 per sensor:** kode sensor putus dan sensor macet. Nilai aslinya tidak terbaca.
- **Logger, 212 baris kunci tidak ada di hasil:** logger mati, pembacaannya tidak pernah tertulis di file mentah.
- **Verifikator, hasil KimFis kosong 1.306:** verifikator tidak menyalinnya. Query mengambil hasil KimFis dari `sensory_kimfis`.
- **Release, hasil 20.636 baris sedangkan kunci 20.634:** selisih 2 adalah baris ALL kedua yang tidak bisa diurai. Ada 7 baris yang batch atau jamnya tidak cocok: 6 di dua batch dengan dua baris ALL, dan 1 salah ketik batch yang jatuh ke batch sah lain di rentang waktu yang sama (`25022331P1` untuk `25022231P1`).
- **Komplain, batch dan DO:** dengan laporan investigasi lengkap, 37 dari 37 tertelusur benar. Tanpa folder laporan, hanya 23 komplain yang menyertakan lot bisa ditelusuri, semuanya benar. Lot dari customer tidak pernah bertentangan dengan laporan.
- **Komplain, justified kosong 1:** komplain yang masih Open.
- **Lab, retest_of kosong 1:** retest lemak yang nilai lemaknya tidak ada di uji pertama maupun di retest.
- **Log kontrol, end_use dan extended kosong 5:** kontrol yang masih dipakai saat data berakhir. Kunci jawaban generator sudah tahu tanggal gantinya, lembar mentah belum.

Baris "tidak dinilai" di keluaran berarti kolom itu ada di kunci tapi sengaja tidak dibuat (misalnya jam sampling di tabel sensory), atau sengaja tidak dibandingkan (catatan sensory, karena teks bebas dengan salah ketik analis dibiarkan apa adanya).

Angka TPC dinilai cocok kalau selisihnya paling banyak 5 %, karena lab menulisnya dengan dua angka penting.

## Bagian 3: assistant

Asisten menjawab dari dokumen dan dari database. Modelnya tidak menulis SQL. Pertanyaan yang menyebut nomor komplain, batch, atau lot menjalankan query yang sudah ditulis dan diuji di `queries.py`, lalu model menjawab dari ringkasan hasil query itu ditambah potongan dokumen.

### `doc_index.py`, pencarian dokumen

1. **Memecah dokumen.** 182 dokumen dipotong per bagian jadi 359 potongan. Judul dokumen ditempel di tiap potongan supaya potongan itu tetap tahu asalnya.
2. **Menyaring revisi.** SOP dan spek punya beberapa revisi. Kode membaca periode di pertanyaan ("Februari 2026", "15 November 2025", atau tanpa tanggal yang berarti hari ini), lalu membuang revisi yang tidak berlaku di periode itu.
3. **Mencari.** Memakai BM25, yaitu pencarian kata kunci yang memberi nilai lebih tinggi untuk kata yang jarang muncul. Kata dipotong dulu dengan stemmer sederhana supaya "berganti" dan "menggantikan" dianggap sama. Aturan (SOP, spek) dan catatan kejadian (NCR, memo, logbook, notulen, investigasi) diperingkat terpisah, masing-masing diambil 3 teratas.

### `queries.py`, query database

| Fungsi | Pertanyaan | Isinya |
|---|---|---|
| `trace_complaint` | komplain ini batch mana | komplain, DO dan customer, customer lain yang menerima batch sama, komplain lain di batch itu, lalu semua isi `batch_status` |
| `batch_status` | batch ini boleh rilis atau tidak | hasil kimia fisika terakhir per sampel dibanding spek yang berlaku di tanggal produksi, sensory dan hasil verifikator untuk sampel yang ditolak, mikro, lot bahan baku per mix beserta keputusan incoming-nya, status release terakhir per mix, pengiriman, komplain untuk batch itu |
| `lot_usage` | lot bahan baku ini dipakai di mana | hasil incoming, mix dan batch yang memakainya, persentase TP3 di mix itu dibanding mix lain grade sama dan periode sama yang tidak memakai lot Conditional atau Reject lain, status release, komplain |
| `verifikator_agreement` | seberapa sering verifikator beda dengan KimFis | persentase sama persis, sama kelas (Pass, TP1, TP2, TP3), dan sama keputusan (diterima atau ditolak), per verifikator, per analis, per grade, tabel silang, dan porsi sampel yang diverifikasi |

Tiap fungsi mengembalikan `text` (ringkasan yang dibaca model) dan `data` (tabel untuk ditampilkan). Nomor yang tidak ada di database dijawab dengan saran nomor yang mirip, misalnya `25062443P1` disarankan `25062434P1`.

Yang disengaja di dalamnya:

- **Pembanding lot dibersihkan dulu.** Di minggu yang sama bisa ada dua lot minyak Conditional. Kalau mix yang memakai lot Conditional lain ikut jadi pembanding, perbedaannya tertutup. Jumlah sampel pembanding ikut ditulis karena kadang kecil (9 sampel untuk PO-250623-01).
- **Angka verifikator diberi peringatan.** Semua TP3 dari KimFis diverifikasi, sedangkan Pass hanya sekitar 27 %. Jadi persentase kesepakatan menggambarkan sampel yang diverifikasi, bukan semua sampel. Kalau porsinya beda lebih dari 1,5 kali, baris `PERINGATAN:` ditaruh di baris kedua hasil query.
- **Angka yang sering dihitung model sudah disediakan.** Persentase yang beda (kebalikan dari yang sama) ditulis langsung, dan status release ditulis "diputuskan oleh ...". Di review pertama, model mengurangkan sendiri 100 % dikurangi 74,8 % dan menganggap orang yang memutuskan release sebagai verifikator.
- **Bahan baku Conditional atau Reject masuk ke baris Temuan** di `batch_status`, supaya tidak tenggelam di baris bahan baku yang panjang.
- **Mix yang di-RECALL ditulis bersama rilis sebelumnya.** Status terakhir saja (RECALL) tidak menjelaskan kenapa barangnya sudah di customer. Baris itu ditambah "sebelumnya RELEASE-URGENT ..., alasan: rilis sebelum hasil mikro".
- **Angka bulat ditulis utuh.** `number()` dulu membuang semua nol di belakang, termasuk pada bilangan bulat, jadi TPC 380 tertulis 38 dan coliform 20 tertulis 2. Hampir semua angka mikro kena (1915 dari 2227 nilai berakhiran nol). Review jawaban v4 tidak menangkapnya karena fakta yang dicek tidak memuat angka mikro. Ketemu saat menyusun pertanyaan holdout, ketika baris Mikro menulis coliform 2 sedangkan baris Temuan menulis coliform 20.
- **Baris Inti di paling atas.** Tiap hasil query dibuka dengan satu baris berisi fakta yang wajib ada di jawaban: status terakhir per mix, hasil di luar spek, bahan baku Conditional, kiriman, dan komplain untuk batch; keputusan incoming, perbandingan TP3, status, dan komplain untuk lot; jumlah sampel dan kesepakatan untuk verifikator. Prompt v5 menyebut baris yang wajib satu per satu, dan model tetap membuang baris yang tidak disebut. Dengan Inti, aturannya cukup satu: isi baris Inti wajib masuk jawaban.
- **Persentase selalu ditulis bersama jumlahnya**, misalnya "27 dari 28 (96,4%)". Di review v5, model menulis 96,4 % tanpa menyebut bahwa itu dari 28 sampel, padahal artinya cuma 1 sampel yang beda.
- **Pembanding lot ditulis dalam satu kalimat dengan angka lot itu.** Di v5 model membuang baris pembanding lalu menyimpulkan lot "menyebabkan" off-flavor tanpa dasar. Kalau TP3 di mix dengan lot itu kurang dari 5, atau pembandingnya kurang dari 30 sampel, ditambah baris PERINGATAN. Dua angka batas ini (`MIN_TP3`, `MIN_COMPARISON`) aturan kira-kira yang dipilih manual, bukan hasil uji statistik. Di data asli, sesuaikan dengan jumlah sampel per minggu di pabrikmu.
- **Sengaja tanpa p-value.** Uji seperti Fisher menganggap tiap sampel independen, padahal 3 sampel dari mix yang sama tidak independen, dan mix dalam satu batch juga saling terkait. P-value dari data per sampel akan terlihat jauh lebih meyakinkan dari kenyataannya. Yang ditulis cukup angka berdampingan dengan jumlahnya.
- **Lot lain di mix yang sama.** Pembanding sudah dibersihkan dari lot Conditional lain, tapi mix yang memakai lot yang ditanya bisa juga memakai lot Conditional lain. Contohnya SMP-250614-01: TP3 5 dari 63 sampel, 3 di antaranya oxid. Ternyata 6 dari 21 mix-nya juga memakai minyak PO-250623-01. Tanpa 6 mix itu, TP3-nya 1 dari 45 sampel, jenis mixgrade. Sekarang angka yang memimpin di baris Inti adalah angka mix yang hanya memakai lot itu, angka campurannya ditulis sesudahnya, dan ada PERINGATAN bahwa TP3 di mix campuran tidak bisa dibebankan ke lot itu saja. Urutannya penting. Di holdout2, waktu angka campuran masih di depan dan angka bersih ada di baris PERINGATAN, semua run menyimpulkan dari angka campuran.

### `assistant.py`, penyusun jawaban

1. **Membaca pertanyaan** (`find_data`). Nomor komplain (`CMP-25-010`) menjalankan `trace_complaint`, lot (`PO-250623-01`, juga `po-250623-1`) menjalankan `lot_usage`, batch (`25062434P1`, juga `25O62434P1` yang diketik dengan huruf O) menjalankan `batch_status` kalau belum tercakup komplain. Kata "verifikator" bersama kata pembanding ("KimFis", "beda", "sama", "sesuai") menjalankan `verifikator_agreement`, dengan periode dan grade dibaca dari pertanyaan. Pertanyaan tentang aturan verifikasi di SOP sengaja tidak masuk ke sini.
2. **Mencari dokumen.** Urutannya tiga:
   - dokumen yang menyebut nomor itu persis, misalnya laporan investigasi komplain;
   - aturan yang dipakai untuk menilai datanya, dicari dengan kata kunci tetap (`RULE_TOPICS`): SOP-QC-012 dan spek grade-nya untuk batch dan komplain, SOP-QC-001 untuk lot, SOP-QC-005 untuk verifikator;
   - hasil pencarian biasa dari pertanyaannya.

   Revisi SOP dan spek untuk batch dipilih menurut tanggal produksi batch itu, bukan hari ini. Batch Juni 2025 dinilai dengan SOP-QC-012 Rev 04 dan SPEC-NDC-28P Rev A (kadar air maks 3,5 %), bukan revisi yang berlaku sekarang. Tanpa ini, model membaca batas 3,2 % dari Rev B untuk batch yang dibuat sebelum Rev B ada.

   Kalau tidak ada revisi yang berlaku di tanggal produksi, pencarian jatuh ke revisi paling awal yang ada. Contohnya batch Januari 2025: SOP-QC-012 paling awal di dokumen adalah Rev 04, yang baru berlaku 01/03/2025 dan baru menambah status RELEASE-URGENT. `rule_notes` mengecek ini dan menambah baris `CATATAN:` ke data, supaya model tidak menilai batch Januari dengan aturan Maret.
3. **Menjawab.** Hasil query dan potongan dokumen masuk ke prompt, lalu Gemini menjawab hanya dari situ.

Kalau database belum dibuat, asisten tetap jalan dengan dokumen saja. Model dan versi prompt diatur di `DEFAULT_MODEL` dan `DEFAULT_PROMPT`.

### `prompts/`, aturan menjawab

| File | Perubahan |
|---|---|
| `jawab_v1.md` | versi pertama, sumber ditulis dengan nomor urut |
| `jawab_v2.md` | sumber ditulis dengan nama dokumen, revisi dan tanggal berlaku disebut |
| `jawab_v3.md` | untuk pertanyaan boleh atau tidak, aturan ditulis dulu baru kesimpulan |
| `jawab_v4.md` | menambah bagian DATA DATABASE: angka dari data, penyebab dan tindakan dari dokumen, status release yang tidak sesuai aturan disebut sebagai temuan |
| `jawab_v5.md` | baris PERINGATAN wajib ditulis, semua temuan disebut (termasuk bahan baku Conditional atau Reject), saran nomor dan alasan status ikut ditulis, dan model tidak boleh menghitung selisih sendiri |
| `jawab_v6.md` | isi baris Inti, PERINGATAN, dan CATATAN wajib masuk jawaban; persentase ditulis dengan jumlahnya; pertanyaan "berpengaruh atau tidak" dibuka dengan kesimpulan dan tidak boleh memakai kata "menyebabkan" dari perbandingan data saja; satuan hanya ditulis kalau ada di data (aturan v5 "lengkap dengan satuannya" membuat model mengarang satuan) |

Versi lama tetap disimpan supaya hasilnya bisa dibandingkan.

### `app.py`, tampilan chat

Aplikasi Streamlit. Tiap pertanyaan dicari sendiri-sendiri, percakapan sebelumnya tidak dikirim ke model. Di bawah tiap jawaban ada ringkasan data database dan daftar potongan dokumen yang dipakai. Batasnya 15 pertanyaan per sesi untuk menjaga kuota gratis.

### `eval/`, pengujian

| File | Fungsi |
|---|---|
| `pertanyaan_dokumen.csv` | 31 pertanyaan uji utama: aturan, catatan kejadian, dan jebakan |
| `pertanyaan_holdout.csv` | 12 pertanyaan yang ditulis sebelum prompt v3 dijalankan dan tidak dipakai untuk menyetel apa pun |
| `run_retrieval_eval.py` | menilai pencarian saja, tanpa Gemini: apakah dokumen yang benar ikut terambil |
| `pertanyaan_data.csv` | 12 pertanyaan untuk bagian database, dengan rute dan fakta yang seharusnya muncul di hasil query. Q12 (batch diketik dengan huruf O) ditambahkan setelah review v4. Kolom `rev` Q04 dikoreksi dari 05 ke 04, karena batch Juni 2025 dinilai dengan SOP-QC-012 Rev 04 (Rev 05 baru berlaku 02/09/2025) |
| `pertanyaan_data_holdout.csv` | 7 pertanyaan database yang ditulis sebelum prompt v5 dijalankan. Sesudah dipakai untuk melihat pola kesalahan v5, set ini bukan holdout lagi, tapi set pengembangan seperti set utama |
| `pertanyaan_data_holdout2.csv` | 9 pertanyaan database baru, ditulis sebelum prompt v6 dijalankan: komplain yang masih Open, batch yang dikirim ke dua customer, mix yang HOLD tanpa keputusan, REWORK, lot tanpa masalah, lot yang tercampur lot Conditional lain, lot bermasalah tanpa komplain, perbandingan VR01 dan VR02, dan RELEASE-URGENT sebelum aturannya ada. Perbaikan query yang ketemu saat menyusunnya (lot lain di mix yang sama) sudah masuk |
| `run_data_eval.py` | menilai rute dan hasil query tanpa Gemini. Hasil saat ini 12 dari 12, holdout 7 dari 7, holdout2 9 dari 9. `--set data_holdout` atau `--set data_holdout2`. Script berhenti kalau ada baris CSV yang kolomnya lebih: koma desimal yang tidak diberi tanda kutip (`1,6%`) memotong kolom fakta, dan di holdout pertama dua fakta sempat tidak pernah dicek karena ini |
| `hasil_data_jawab_v4.csv` | jawaban Gemini untuk 11 pertanyaan database dengan prompt v4, sudah direview: 5 benar, 5 sebagian, 1 salah |
| `hasil_data_jawab_v5.csv` | prompt v5 di set utama, sudah direview: 9 benar, 3 sebagian. Di 11 pertanyaan yang sama dengan v4: 8 benar, 3 sebagian |
| `hasil_data_holdout_jawab_v5.csv` | prompt v5 di holdout, sudah direview: 3 benar, 4 sebagian |
| `hasil_data_holdout_jawab_v5_ulang.csv` | holdout yang sama dijalankan ulang dengan flash-lite: 3 benar, 3 sebagian, 1 salah. Jumlah benarnya sama dengan run pertama, tapi 3 dari 7 pertanyaan berganti penilaian. Selisih satu dua pertanyaan antar versi prompt dari satu run saja belum berarti apa-apa |
| `hasil_data_holdout2_jawab_v6.csv`, `..._ulang.csv`, `..._gemini-3.6-flash.csv` | prompt v6 di holdout2, sudah direview: flash-lite 5 benar, 3 sebagian, 1 salah dan 7 benar, 2 sebagian; Flash 6 benar, 1 salah dari 7 yang terjawab |
| `hasil_data_holdout_jawab_v5_gemini-3.6-flash.csv` | holdout yang sama dengan `gemini-3.6-flash`: 6 benar, 1 salah. Baris yang dibuang flash-lite (pembanding, rilis urgent sebelum recall, jumlah sampel) ditulis lengkap. Salahnya di H05: menyimpulkan lot berpengaruh dari 1 TP3 mixgrade, sama dengan run ulang flash-lite. Menilai bukti yang lemah gagal di kedua model, jadi penilaian itu dipindah ke query |
| `run_answer_eval.py` | mengirim pertanyaan ke Gemini dan menyimpan jawabannya, bisa dilanjutkan kalau berhenti di tengah. `--set data` untuk pertanyaan database, `--set data_holdout` dan `--set data_holdout2` untuk holdout-nya. `--model` untuk mencoba model lain dan `--tag` untuk mengulang run yang sama. Keduanya menambah nama file hasil, jadi file yang sudah direview tidak tertimpa |
| `hasil_*.csv` | jawaban Gemini beserta penilaian manual di kolom `cek_manual` dan `catatan_review` |

Kolom `cek_otomatis` cuma mencocokkan kata kunci dan pernah meloloskan jawaban yang salah. Penilaian yang dipegang adalah `cek_manual`.

## Menyesuaikan untuk data sendiri

Urutan kerjanya sama, yang berubah isi tiap langkah.

1. **Profiling dulu.** Untuk tiap kolom, lihat jumlah nilai unik dan contoh nilainya, lalu catat yang tidak seragam. Contohnya ada di `work/01_profiling.ipynb`.
2. **Arahkan ke folder datamu.** Ubah `RAW_DIR` di bagian atas `common.py`, lalu isi `folder` dan `pola_file` di `sumber_data.csv`. Matikan tabel yang datanya belum didapat.
3. **Isi `kolom.csv`** dengan judul kolom di file aslimu. Tandai `wajib` hanya untuk kolom yang benar-benar dibutuhkan, supaya departemen lain yang memberi data sebagian tetap bisa diproses.
4. **Tentukan kunci penyambung.** Di sini `batch_no`, `mix_id`, dan `sample_uid`. Pastikan dulu cara tiap departemen menomori batch, mix, dan sampel. Di data ini log produksi dan lab ternyata menomori mix dengan cara berbeda.
5. **Bersihkan tabel induk lebih dulu**, yaitu tabel yang paling bisa dipercaya untuk daftar batch. Tabel lain diperbaiki dengan mencocokkan ke tabel itu.
6. **Isi tabel padanan** dengan penulisan grade, nama analis, supplier, customer, status, dan bahan yang dipakai di tempatmu. Isi `spek_produk.csv` dari DCIS.
7. **Sesuaikan `batas_wajar.csv`** untuk salah koma, satuan, dan kode sensor alatmu.

Tiga hal yang tidak bisa disalin begitu saja:

- **Tidak ada kunci jawaban di data asli.** `check_against_key.py` hanya jalan untuk data generator. Penggantinya pengecekan seperti jumlah baris per bulan, rentang nilai per grade, dan persentase baris yang berhasil disambungkan antar tabel.
- **Beberapa keputusan di sini diambil dengan melihat kunci jawaban**, dan di data asli harus ditanyakan ke orang yang mengisi datanya: entri lab ganda (yang disimpan entri pertama), dua pembacaan logger di jam yang sama (dua-duanya disimpan), batas sensor macet (16 pembacaan), arti `ALL` dan `E-G` di log release, rentang hari yang dipakai `nearest_batch` (kirim paling lama 30 hari, verifikasi 1 sampai 2 hari, QUARANTINE 2 hari setelah produksi), dan jeda 30 menit yang memisahkan dua transisi grade retail.
- **Data asli perusahaan jangan masuk ke repo publik atau ke API gratis.** Pipeline bisa dijalankan sepenuhnya di laptop tanpa internet. Yang mengirim data keluar hanya bagian asisten, saat memanggil Gemini.

## Status asisten

Bagian asisten dibekukan di prompt v6. Perjalanannya, untuk pertanyaan database:

| Versi | Set | Hasil (benar) |
|---|---|---|
| v4 | set utama, 11 pertanyaan | 5, ditambah 5 sebagian dan 1 salah |
| v5 | set utama, 11 pertanyaan yang sama | 8, tapi perbaikannya dirancang dari pertanyaan yang sama |
| v5 | holdout pertama, 7 pertanyaan | 3 dan 3 di dua run flash-lite, 6 dengan Flash |
| v6 | holdout2, 9 pertanyaan | 5 dan 7 di dua run flash-lite, 6 dari 7 yang terjawab dengan Flash |

Yang dipelajari:

- Hasil flash-lite berubah-ubah antar run. Selisih satu dua pertanyaan dari satu run saja belum berarti apa-apa.
- Model membuang baris yang memberi arti pada angka (pembanding, jumlah sampel, alasan). Menyebut baris itu satu per satu di prompt cuma menambal kasus yang ketahuan. Yang lebih jalan adalah menaruh fakta wajib di satu baris Inti dan menulis persentase bersama jumlahnya.
- Menilai bukti yang lemah gagal di kedua model, jadi penilaian itu dikerjakan query (PERINGATAN), bukan model. Urutan di baris Inti juga ikut menentukan: angka yang ditaruh di depan yang dipakai model untuk menyimpulkan.

Sesudah holdout2 ada satu perbaikan di query (D06, angka bersih memimpin di baris Inti). Perbaikan itu belum diuji di pertanyaan baru. Iterasi dihentikan di sini karena masalah yang tersisa, flash-lite kadang membuang baris wajib, adalah batas modelnya, dan tiap putaran baru butuh holdout baru.

## Yang belum dikerjakan

- D08 dan D09 holdout2 dengan `gemini-3.6-flash`. Run berhenti di D07, lalu kena batas kuota harian gratis waktu dilanjutkan. Kuota gratis Flash terlalu kecil untuk app yang membatasi 15 pertanyaan per sesi, jadi app tetap memakai flash-lite.
- Spektrum NIRS (`NIRS_Spectra_*.csv.gz`).
- Formula dari RND, menunggu data. Tempatnya sudah disiapkan di config.
- Umur simpan di dokumen spesifikasi generator. COA Checker sudah memakainya, tapi dokumen SPEC belum memuatnya.
