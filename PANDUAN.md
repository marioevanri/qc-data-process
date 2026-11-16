# Panduan qc-data-process

Catatan ini menjelaskan isi repo: tiap folder, tiap script, urutan menjalankannya, dan bagian mana yang perlu diubah kalau dipakai untuk data lain. Semua data di sini fiktif, pabriknya PT Sari Krimer Nusantara buatan generator.

## Gambaran besar

Repo ini punya tiga bagian yang berurutan.

| Folder | Isi | Hasilnya |
|---|---|---|
| `generator/` | pembuat data dan dokumen pabrik fiktif | file mentah per departemen di `generator/data/raw` dan sekitar 180 dokumen di `generator/docs` |
| `pipeline/` | pembersih data mentah | satu database SQLite, `db/qc.db` |
| `assistant/` | asisten QC berbasis chat | jawaban dari dokumen, nanti juga dari database |

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

## Bagian 2: pipeline

Pipeline mengubah file mentah jadi tabel bersih di satu database. Tiap departemen punya satu script `clean_*.py`.

### `common.py`, alat bantu bersama

Fungsi kecil yang dipakai semua script cleaning. Kalau pindah ke data lain, file ini yang paling banyak disesuaikan.

| Fungsi | Yang dikerjakan | Contoh |
|---|---|---|
| `read_raw` | membaca file sebagai teks dan mendeteksi pemisah `,` atau `;` | file dari Excel berbahasa Indonesia memakai `;` |
| `clean_grade` | menyeragamkan nama grade lewat tabel padanan | `NDC 28P`, `ndc-28p`, `Krimer 35` |
| `clean_batch` | membuang garis miring, spasi, dan tanda hubung | `250102/61/RT` jadi `25010261RT` |
| `clean_lot` | merapikan nomor lot bahan baku | `po-250103-1` jadi `PO-250103-01` |
| `clean_analyst` | mengubah nama analis jadi ID | `Andi`, `ANDI`, `Andi P.` jadi `AN01` |
| `clean_time` | menyamakan penulisan jam | `10.31` jadi `10:31` |
| `to_number` | teks jadi angka, menerima koma desimal | `2,66` jadi 2.66, `ND` jadi kosong |
| `fix_decimal_shift` | membagi 10 nilai di atas batas wajar | suhu inlet `1827.3` jadi 182.73 |
| `fix_decimal_shift_by_group` | sama, tapi batasnya 4 kali median per grade | protein 2 % di krimer dan 20 % di susu |
| `after_shift_start` | menentukan tanggal kalender dari tanggal produksi dan jam | sampel jam 02.00 terjadi di hari berikutnya |

Semua data dibaca sebagai teks dulu, baru diubah ke angka atau tanggal satu kolom demi satu kolom. Kalau langsung dibaca sebagai angka, nilai seperti `2,66` atau `?` membuat pandas menebak sendiri dan kesalahannya tidak kelihatan.

### `config/`, tabel padanan

| File | Isi |
|---|---|
| `padanan_grade.csv` | cara penulisan grade dan kode bakunya |
| `padanan_analis.csv` | nama depan analis dan ID-nya |

Penulisan dicocokkan setelah diubah ke huruf kecil dan dibuang spasi serta tanda bacanya. Jadi `NDC 28P` dan `ndc-28p` cukup satu baris, `ndc28p`. Kalau ada penulisan baru, tambah baris di sini tanpa mengubah kode.

### `clean_production.py`, log produksi

Satu baris per mix. Tabel ini dikerjakan pertama karena kuncinya (`batch_no` dan `mix_id`) dipakai untuk memperbaiki dan menyambungkan tabel lain.

1. Buang baris duplikat.
2. Seragamkan line, grade, batch, dan nomor lot.
3. Susun jam mulai dan selesai. Hari produksi berjalan 07.00 sampai 07.00, jadi mix jam 02.00 masih milik tanggal sebelumnya.
4. Tentukan huruf mix. Kolom Mix No di log produksi menghitung mix per line per hari, sedangkan lab dan sensory memakai huruf yang menghitung mix per nomor batch. Jadi huruf ditentukan dari urutan jam mulai di dalam satu batch, yang pertama A.
5. Ubah kolom angka dan perbaiki salah koma.

### `clean_lab.py`, hasil uji KimFis

Satu baris per pengujian sampel, dari 19 file bulanan.

1. Gabung semua file dan samakan nama kolom. Lembar ini berubah di Januari 2026, misalnya `Visko (cP)` jadi `Viskositas (cP)`.
2. Perbaiki identitas sampel: grade, batch, kode sampel, analis. Batch yang salah ketik dicari di log produksi lewat tanggal, grade, dan line. Tanggal produksi dibaca dari nomor batch, karena untuk sampel lewat tengah malam sebagian analis menulis tanggal kalender.
3. Susun jam sampling dan jam uji. Jam sampling dibandingkan dengan jam mulai mix-nya, supaya sampel terakhir mix malam yang diambil sesudah 07.00 tetap jatuh di hari yang benar.
4. Ubah angka. Bulk density yang ditulis dalam g/L dibagi 1000, salah koma dibagi 10.
5. Buang entri yang diketik dua kali untuk sampel dan jam uji yang sama. Yang disimpan entri pertama.
6. Tandai retest, yaitu sampel yang sama diuji lagi di jam yang berbeda.

### `build_db.py`, pembuat database

Menjalankan semua script cleaning dan menulis hasilnya ke `db/qc.db`. Daftar tabelnya ada di `TABLES` di bagian atas file. Departemen baru cukup didaftarkan di sana.

File database tidak ikut ke GitHub. Siapa pun bisa membuatnya ulang dengan perintah yang sama.

### `check_against_key.py`, penilai hasil cleaning

Membandingkan tiap tabel di database dengan kunci jawaban generator, kolom per kolom. Keluarannya tiga angka per kolom:

- **cocok**: sama dengan kunci, dalam toleransi pembulatan.
- **beda**: ada nilainya tapi tidak sama dengan kunci. Ini yang harus diselidiki.
- **kosong**: di kunci ada nilainya, di hasil cleaning kosong. Biasanya karena di data mentah memang kosong atau berisi teks.

Hasil saat ini:

| Tabel | Baris mentah | Baris bersih | Kolom yang beda |
|---|---|---|---|
| `production_mix_log` | 10.036 | 9.942 | tidak ada |
| `qc_lab_kimfis` | 30.500 | 29.927 | kadar air 21, viskositas 22, Brix 19 |

Yang beda di lab berasal dari sekitar 20 pasang sampel yang kodenya tertukar saat diketik. Itu tidak bisa diperbaiki dari datanya sendiri.

## Bagian 3: assistant

Asisten menjawab pertanyaan dari dokumen. Sambungan ke database belum dibuat.

### `doc_index.py`, pencarian dokumen

1. **Memecah dokumen.** 182 dokumen dipotong per bagian jadi 359 potongan. Judul dokumen ditempel di tiap potongan supaya potongan itu tetap tahu asalnya.
2. **Menyaring revisi.** SOP dan spek punya beberapa revisi. Kode membaca periode di pertanyaan ("Februari 2026", "15 November 2025", atau tanpa tanggal yang berarti hari ini), lalu membuang revisi yang tidak berlaku di periode itu.
3. **Mencari.** Memakai BM25, yaitu pencarian kata kunci yang memberi nilai lebih tinggi untuk kata yang jarang muncul. Kata dipotong dulu dengan stemmer sederhana supaya "berganti" dan "menggantikan" dianggap sama. Aturan (SOP, spek) dan catatan kejadian (NCR, memo, logbook, notulen, investigasi) diperingkat terpisah, masing-masing diambil 3 teratas.

### `assistant.py`, penyusun jawaban

Memanggil pencarian, menyusun potongan yang didapat jadi satu teks dengan baris "Sumber:" di tiap potongan, lalu meminta Gemini menjawab hanya dari teks itu. Model dan versi prompt diatur di `DEFAULT_MODEL` dan `DEFAULT_PROMPT`.

### `prompts/`, aturan menjawab

| File | Perubahan |
|---|---|
| `jawab_v1.md` | versi pertama, sumber ditulis dengan nomor urut |
| `jawab_v2.md` | sumber ditulis dengan nama dokumen, revisi dan tanggal berlaku disebut |
| `jawab_v3.md` | untuk pertanyaan boleh atau tidak, aturan ditulis dulu baru kesimpulan |

Versi lama tetap disimpan supaya hasilnya bisa dibandingkan.

### `app.py`, tampilan chat

Aplikasi Streamlit. Tiap pertanyaan dicari sendiri-sendiri, percakapan sebelumnya tidak dikirim ke model. Di bawah tiap jawaban ada daftar potongan dokumen yang dipakai. Batasnya 15 pertanyaan per sesi untuk menjaga kuota gratis.

### `eval/`, pengujian

| File | Fungsi |
|---|---|
| `pertanyaan_dokumen.csv` | 31 pertanyaan uji utama: aturan, catatan kejadian, dan jebakan |
| `pertanyaan_holdout.csv` | 12 pertanyaan yang ditulis sebelum prompt v3 dijalankan dan tidak dipakai untuk menyetel apa pun |
| `run_retrieval_eval.py` | menilai pencarian saja, tanpa Gemini: apakah dokumen yang benar ikut terambil |
| `run_answer_eval.py` | mengirim pertanyaan ke Gemini dan menyimpan jawabannya, bisa dilanjutkan kalau berhenti di tengah |
| `hasil_*.csv` | jawaban Gemini beserta penilaian manual di kolom `cek_manual` dan `catatan_review` |

Kolom `cek_otomatis` cuma mencocokkan kata kunci dan pernah meloloskan jawaban yang salah. Penilaian yang dipegang adalah `cek_manual`.

## Menyesuaikan untuk data sendiri

Urutan kerjanya sama, yang berubah isi tiap langkah.

1. **Profiling dulu.** Untuk tiap kolom, lihat jumlah nilai unik dan contoh nilainya, lalu catat yang tidak seragam. Contohnya ada di `work/01_profiling.ipynb`.
2. **Tentukan kunci penyambung.** Di sini `batch_no`, `mix_id`, dan `sample_uid`. Pastikan dulu cara tiap departemen menomori batch, mix, dan sampel. Di data ini log produksi dan lab ternyata menomori mix dengan cara berbeda.
3. **Bersihkan tabel induk lebih dulu**, yaitu tabel yang paling bisa dipercaya untuk daftar batch. Tabel lain diperbaiki dengan mencocokkan ke tabel itu.
4. **Isi tabel padanan** di `pipeline/config` dengan penulisan grade dan nama analis yang dipakai di tempatmu.
5. **Sesuaikan `RENAME`** di tiap script cleaning dengan nama kolom di file aslimu.
6. **Sesuaikan batas wajar** untuk salah koma dan satuan.

Tiga hal yang tidak bisa disalin begitu saja:

- **Tidak ada kunci jawaban di data asli.** `check_against_key.py` hanya jalan untuk data generator. Penggantinya pengecekan seperti jumlah baris per bulan, rentang nilai per grade, dan persentase baris yang berhasil disambungkan antar tabel.
- **Keputusan seperti "entri ganda, simpan yang mana" harus ditanyakan** ke orang yang mengisi datanya. Di sini keputusannya diambil dengan melihat kunci jawaban.
- **Data asli perusahaan jangan masuk ke repo publik atau ke API gratis.** Pipeline bisa dijalankan sepenuhnya di laptop tanpa internet. Yang mengirim data keluar hanya bagian asisten, saat memanggil Gemini.

## Yang belum dikerjakan

- Cleaning untuk sensory, mikro, dan departemen lain.
- Fungsi query ke database dan sambungannya ke asisten.
- Kolom `retest_of` di tabel lab (parameter yang memicu retest).
- Umur simpan di dokumen spesifikasi generator. COA Checker sudah memakainya, tapi dokumen SPEC belum memuatnya.
