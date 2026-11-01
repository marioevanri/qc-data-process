# Static controlled documents: SOPs and specifications.
# Some SOPs exist in two revisions on purpose, a RAG system has to pick the one valid
# on the date the question is about.

import config as C

CO = C.COMPANY


def header(no, title, rev, berlaku, disusun="Agus Salim (QC Supervisor)", disetujui="Ratna Kusuma (QA Manager)",
           status="Berlaku"):
    return (f"# {title}\n\n"
            f"| | |\n|---|---|\n| No. Dokumen | {no} |\n| Revisi | {rev} |\n| Tanggal Berlaku | {berlaku} |\n"
            f"| Status | {status} |\n| Disusun | {disusun} |\n| Disetujui | {disetujui} |\n| Perusahaan | {CO} |\n\n")


SOP_RM = header("SOP-QC-001", "Penerimaan dan Inspeksi Bahan Baku", "03", "01/11/2024") + """
## 1. Tujuan
Memastikan bahan baku utama yang masuk ke gudang sudah diperiksa QC sebelum dipakai produksi, dan setiap lot bisa ditelusuri sampai ke supplier.

## 2. Ruang Lingkup
Berlaku untuk minyak nabati (Hydrogenated Coconut Oil dan RBD Palm Oil), Glucose Syrup Solids DE 30, Sodium Caseinate, dan Skim Milk Powder. Bahan tambahan minor (emulsifier, stabilizer, flavor) diatur di SOP-QC-002.

## 3. Tanggung Jawab
QC Bahan Baku melakukan sampling, pengujian, dan keputusan. Gudang tidak boleh mengeluarkan lot yang belum berstatus release. Purchasing wajib menginformasikan QC paling lambat 2 minggu sebelum kedatangan pertama jika ada supplier baru atau perubahan spesifikasi bahan.

## 4. Prosedur

### 4.1 Pemeriksaan dokumen
Setiap kedatangan wajib disertai COA dari supplier. Kalau COA tidak ada, sampel tetap boleh diambil dan diuji, tapi lot tidak boleh di-release sampai COA diterima. Cocokkan nomor lot supplier di COA dengan label kemasan atau segel tangki.

### 4.2 Sampling
Minyak dari tangki truk diambil di 3 titik (atas, tengah, bawah) lalu dikomposit 1 liter. Bahan serbuk diambil dari akar(n)+1 karung, n adalah jumlah karung dalam satu kedatangan, dikomposit lalu dibagi untuk uji kimia dan mikro.

### 4.3 Parameter dan batas

| Bahan | Parameter | Batas |
|---|---|---|
| HCO, RBD Palm Oil | FFA | maks 0,10 % |
| HCO, RBD Palm Oil | Peroxide Value (PV) | maks 2,0 meq O2/kg |
| HCO, RBD Palm Oil | Kadar air | maks 0,10 % |
| HCO, RBD Palm Oil | Warna Lovibond (merah) | maks 3,0 |
| Glucose Syrup Solids | DE | 28 sampai 32 |
| Glucose Syrup Solids | Kadar air | maks 5,0 % |
| Glucose Syrup Solids | pH (larutan 10%) | 4,5 sampai 5,5 |
| Sodium Caseinate | Protein | min 88,0 % |
| Sodium Caseinate | Kadar air | maks 6,0 % |
| Sodium Caseinate | pH (larutan 5%) | 6,4 sampai 7,0 |
| Skim Milk Powder | Protein | min 34,0 % |
| Skim Milk Powder | Kadar air | maks 4,0 % |
| Skim Milk Powder | Lemak | maks 1,25 % |
| Skim Milk Powder | Indeks kelarutan | maks 1,0 ml |
| Skim Milk Powder | TPC | maks 10.000 cfu/g |

DE Glucose Syrup Solids cukup diuji QC minimal 1 dari 3 lot. Lot yang tidak diuji mengacu ke nilai COA.

### 4.4 Keputusan
Accept kalau semua parameter di dalam batas. Conditional kalau masih di dalam batas tapi mendekati, yaitu FFA di atas 0,085 %, PV 1,5 meq/kg atau lebih, DE di luar 28,5 sampai 31,5, warna merah di atas 3,0, pH di luar range, lemak SMP di atas 1,25 %, atau kelarutan SMP di atas 1,0 ml. Lot Conditional boleh dipakai dengan catatan "pakai segera", diprioritaskan FIFO, dan QC wajib menginformasikan PPIC. Reject kalau ada parameter wajib yang keluar batas, lot dikembalikan ke supplier dan dibuatkan NCR.

### 4.5 Release dan penomoran lot
Lot di-release 1 hari setelah diterima. SMP menunggu hasil mikro, sekitar 4 hari. Lot internal diberi nomor KODE-YYMMDD-NN, contoh PO-250908-01 untuk RBD Palm Oil kedatangan pertama tanggal 8 September 2025. Kode bahan: HCO, PO, GSS, CAS, SMP.

## 5. Riwayat Revisi

| Rev | Tanggal | Perubahan |
|---|---|---|
| 02 | 15/03/2023 | Penambahan uji PV untuk semua lot minyak |
| 03 | 01/11/2024 | Kategori Conditional, DE GSS minimal 1 dari 3 lot, kewajiban Purchasing info supplier baru |
"""

SENSORY_COMMON = """
## 3. Penguji
Uji rutin dilakukan analis KimFis yang bertugas di shift tersebut, satu orang per shift. Verifikator menguji ulang sampel retain pada H+1 (hari kerja berikutnya). Verifikator tidak bekerja hari Minggu, sampel Sabtu dan Minggu diverifikasi hari Senin.

## 4. Sampel
Setiap mix diambil 3 titik: 1 awal, 2 tengah, 3 akhir proses spray drying. Kode sampel adalah huruf mix diikuti angka titik, contoh A1, A2, A3, B1. Huruf mix berurutan per nomor batch, tidak di-reset saat ganti shift.

Penyajian: krimer 10 g dalam 150 ml air 70 C, susu bubuk 25 g dalam 200 ml air 50 C. Sampel dan kontrol disajikan berdampingan dalam gelas yang sama.

## 5. Kontrol (pembanding)
Setiap grade punya sampel kontrol sebagai acuan nilai 0. Kontrol diambil dari batch produksi terbaru yang dinilai paling mendekati kontrol lama oleh verifikator. Masa pakai kontrol 30 hari untuk grade berbasis RBD Palm Oil (NDC-28P, FMP-26, MLK-RT) dan 90 hari untuk grade lain (NDC-35, CRM-RT), karena minyak sawit lebih cepat berubah aroma.
"""

SOP_SENS_02 = header("SOP-QC-005", "Uji Sensory Produk Jadi", "02", "03/06/2024",
                     status="Tidak berlaku, digantikan Rev 03 per 05/01/2026") + """
## 1. Tujuan
Menilai kesesuaian rasa dan aroma produk jadi terhadap kontrol sebelum produk di-release.

## 2. Ruang Lingkup
Semua grade produk jadi di Plant 1, Plant 2, dan Line Retail.
""" + SENSORY_COMMON + """
Kalau kontrol baru belum tersedia saat jatuh tempo, kontrol lama boleh diperpanjang sampai kontrol baru siap.

## 6. Atribut dan skala
Atribut yang dinilai: creamy, mouthfeel, milky, dan manis, ditambah pengecekan off-flavor (tengik, gosong, apek, asing, rasa campur grade sebelumnya). Skala ditulis dengan kata:

| Kata | Arti |
|---|---|
| kurang | jauh di bawah kontrol |
| agak kurang | sedikit di bawah kontrol |
| pass | sama dengan kontrol |
| agak lebih | sedikit di atas kontrol |
| lebih | jauh di atas kontrol |

## 7. Penentuan grade
Pass kalau semua atribut "pass" dan tidak ada off-flavor. TP1+ atau TP1- kalau ada atribut agak lebih atau agak kurang. TP2+ atau TP2- kalau ada atribut lebih atau kurang. TP3 kalau ada off-flavor, apa pun nilai atributnya. Tanda + atau - mengikuti atribut dengan deviasi terbesar, kalau sama besar prioritasnya creamy, mouthfeel, milky, lalu manis.

## 8. Tindak lanjut
TP1 boleh release dengan catatan. TP2 dan TP3 wajib hold dan menunggu hasil verifikator H+1. Verifikator menguji 25 % sampel acak setiap hari ditambah semua sampel TP2 dan TP3.
"""

SOP_SENS_03 = header("SOP-QC-005", "Uji Sensory Produk Jadi", "03", "05/01/2026") + """
## 1. Tujuan
Menilai kesesuaian rasa dan aroma produk jadi terhadap kontrol sebelum produk di-release.

## 2. Ruang Lingkup
Semua grade produk jadi di Plant 1, Plant 2, dan Line Retail.
""" + SENSORY_COMMON + """
Perpanjangan kontrol maksimal 14 hari setelah jatuh tempo dan harus disetujui QC Supervisor. Kalau sampai 14 hari kontrol baru belum ada, wajib dibuat kontrol sementara dari batch terbaru yang disetujui verifikator. ID kontrol wajib ditulis di lembar sensory.

## 6. Atribut dan skala
Atribut sama seperti revisi sebelumnya: creamy, mouthfeel, milky, manis, dan off-flavor. Mulai revisi ini skala ditulis dengan angka supaya mudah diolah:

| Angka | Arti | Padanan Rev 02 |
|---|---|---|
| -2 | jauh di bawah kontrol | kurang |
| -1 | sedikit di bawah kontrol | agak kurang |
| 0 | sama dengan kontrol | pass |
| +1 | sedikit di atas kontrol | agak lebih |
| +2 | jauh di atas kontrol | lebih |

## 7. Penentuan grade
Aturan grade tidak berubah. Pass kalau semua atribut 0 dan tidak ada off-flavor, TP1 kalau ada nilai -1 atau +1, TP2 kalau ada -2 atau +2, TP3 kalau ada off-flavor.

## 8. Tindak lanjut
TP1 boleh release dengan catatan. TP2 dan TP3 wajib hold dan menunggu hasil verifikator H+1. Porsi verifikasi acak naik dari 25 % menjadi 30 % sampel per hari, ditambah semua sampel TP2 dan TP3.

## 9. Riwayat Revisi

| Rev | Tanggal | Perubahan |
|---|---|---|
| 02 | 03/06/2024 | Kode sampel 3 titik per mix, masa pakai kontrol per jenis minyak |
| 03 | 05/01/2026 | Skala angka, ID kontrol wajib, batas perpanjangan kontrol 14 hari, verifikasi 30 % |
"""

SOP_VISC = header("SOP-QC-007", "Pengukuran Viskositas dan Brix Larutan Rekonstitusi", "01", "01/08/2023") + f"""
## 1. Tujuan
Mengukur viskositas dan Brix larutan produk sebagai indikator konsistensi formula dan proses.

## 2. Persiapan larutan
Timbang 20,0 g sampel, larutkan dengan air demineral sampai 100 ml (konsentrasi {C.RECON_CONC_PCT:.0f} % b/v). Aduk 2 menit, diamkan sampai suhu 25 +/- 0,5 C.

## 3. Viskositas
Gunakan viskometer rotasi spindle LV-1 pada 60 rpm. Baca nilai setelah 60 detik dalam cP. Sebelum pengukuran pertama setiap shift, cek alat dengan cairan standar 5,0 cP. Kalau hasil cek di luar 4,8 sampai 5,2 cP, alat tidak boleh dipakai dan lapor QC Supervisor. Kalibrasi eksternal setiap 6 bulan.

## 4. Brix
Teteskan larutan yang sama ke refraktometer digital, catat 1 desimal. Bersihkan prisma dengan air demineral setiap pergantian sampel. Cek nol dengan air demineral setiap awal shift.

## 5. Retest
Kalau viskositas, kadar air, atau lemak di luar spesifikasi, ulangi sekali dengan larutan baru dari sampel yang sama. Nilai retest yang dipakai untuk keputusan release, dan baris retest ditandai di lembar KimFis.

## 6. Catatan
Viskositas dipengaruhi kadar protein, fungsi protein (sodium caseinate atau SMP), dan ukuran globula lemak. Penurunan viskositas yang konsisten di banyak batch biasanya bukan masalah pengukuran, tetap cek alat dulu sebelum menyimpulkan.
"""

SOP_NIRS = header("SOP-QC-009", "Analisa NIRS Serbuk", "02", "10/02/2025") + """
## 1. Tujuan
Memantau kadar air, lemak, dan protein produk jadi secara cepat di setiap titik sampel. NIRS dipakai untuk monitoring, keputusan release tetap memakai metode referensi (moisture analyzer untuk kadar air, metode ekstraksi untuk lemak, Kjeldahl untuk protein).

## 2. Alat
NIRS DS-01, mode reflektansi, rentang 1100 sampai 2500 nm, cawan putar. Model prediksi dipisah per grade: NDC35_v3, NDC28P_v2, FMP26_v1, CRMRT_v2, MLKRT_v1.

## 3. Prosedur
Isi cawan dengan serbuk dari sampel hopper sampai penuh, ratakan tanpa ditekan. Sebelum sampel pertama tiap grade tiap hari, scan sampel kontrol grade tersebut. Kalau prediksi kadar air kontrol bergeser lebih dari 0,2 % dari nilai acuan kontrol, hentikan pengukuran dan lapor QC Supervisor.

Penamaan sampel di software: "<No Batch> <Kode Sampel>", contoh "25090834P2 B2". Kontrol dinamai dengan ID kontrol, contoh "CTRL-34-012".

## 4. Perawatan
Lampu diganti sekitar 12 bulan sekali atau saat energi lampu di bawah batas software. Setelah ganti lampu, wajib cek bias dengan minimal 10 sampel yang punya hasil referensi, dan model dikoreksi kalau bias kadar air lebih dari 0,1 %.

## 5. Riwayat Revisi

| Rev | Tanggal | Perubahan |
|---|---|---|
| 01 | 01/07/2023 | Dokumen baru |
| 02 | 10/02/2025 | Scan kontrol per grade per hari, aturan cek bias setelah ganti lampu |
"""

HOLD_COMMON = """
## 3. Status produk

| Status | Arti |
|---|---|
| QUARANTINE | produk baru dikemas, menunggu hasil QC |
| HOLD | ditahan karena ada hasil di luar spek atau sensory TP2/TP3 |
| RELEASE | boleh dikirim |
| RELEASE-URGENT | release bersyarat sebelum hasil mikro keluar |
| BLEND | dicampur ke mix yang pass, rasio maksimal 1:4 |
| REWORK | diproses ulang, misalnya dikeringkan ulang |
| REJECT | tidak boleh dipakai |
| RECALL | ditarik dari customer |

## 4. Kriteria hold
Mix di-hold kalau ada salah satu kondisi berikut: kadar air, viskositas, lemak, bulk density, kelarutan, atau warna di luar spesifikasi setelah retest, coffee test gagal untuk grade yang wajib coffee test, sensory TP2 atau TP3, atau hasil mikro TMS.

## 5. Release normal
Release dilakukan setelah semua hasil fisik-kimia dan sensory memenuhi syarat dan hasil mikro TPC, coliform, kapang khamir sudah keluar (H+3). Salmonella keluar H+5, release boleh mendahului hasil Salmonella.

## 6. Disposisi produk hold
Off-flavor tengik atau gosong yang dikonfirmasi verifikator: REJECT. Kadar air di atas spek: REWORK. Sensory TP2, coffee test gagal, atau rasa campur grade: BLEND. Kalau verifikator tidak mengkonfirmasi temuan analis, produk boleh RELEASE dengan persetujuan QC Supervisor. Hasil mikro TMS: REJECT, dan kalau produk sudah terkirim: RECALL.
"""

def hold_sops():
    # Rev 05 exists only when this factory had a CIP recall that triggered it
    rev = C.SOP_HOLD_REV05_DATE
    has05 = rev is not None and rev <= C.END_DATE
    status = f"Tidak berlaku, digantikan Rev 05 per {rev:%d/%m/%Y}" if has05 else "Berlaku"
    rev04 = header("SOP-QC-012", "Hold, Release, dan Disposisi Produk", "04", "01/03/2025", status=status) + """
## 1. Tujuan
Mengatur status produk jadi dari selesai dikemas sampai boleh dikirim, ditahan, atau dimusnahkan.

## 2. Ruang Lingkup
Semua produk jadi B2B dan retail.
""" + HOLD_COMMON + """
## 7. Release urgent
RELEASE-URGENT boleh dilakukan sebelum hasil mikro kalau ada permintaan tertulis dari PPIC, semua hasil fisik-kimia dan sensory sudah OK, dan disetujui QA Manager. Kalau hasil mikro kemudian TMS, produk ditarik (RECALL).
"""
    docs = {"sop/SOP-QC-012_Hold_Release_Disposisi_Rev04.md": rev04}
    if has05:
        cip = next(e for e in C.EVENTS if e["kind"] == "cip_failure")
        bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"][cip["start"].month - 1]
        docs["sop/SOP-QC-012_Hold_Release_Disposisi_Rev05.md"] = header(
            "SOP-QC-012", "Hold, Release, dan Disposisi Produk", "05", f"{rev:%d/%m/%Y}") + """
## 1. Tujuan
Mengatur status produk jadi dari selesai dikemas sampai boleh dikirim, ditahan, atau dimusnahkan.

## 2. Ruang Lingkup
Semua produk jadi B2B dan retail.
""" + HOLD_COMMON + f"""
## 7. Release urgent
Menindaklanjuti recall {bulan} {cip["start"].year}, RELEASE-URGENT tidak diperbolehkan lagi untuk produk retail (CRM-RT, MLK-RT). Untuk produk B2B masih boleh, dengan syarat tambahan hasil baca awal TPC 48 jam sudah keluar dan memenuhi syarat, permintaan tertulis PPIC, dan persetujuan QA Manager.

## 8. Riwayat Revisi

| Rev | Tanggal | Perubahan |
|---|---|---|
| 04 | 01/03/2025 | Penambahan status RELEASE-URGENT dan RECALL |
| 05 | {rev:%d/%m/%Y} | Release urgent dilarang untuk retail, B2B wajib baca awal TPC 48 jam |
"""
    return docs


SOP_TRANS = header("SOP-QC-015", "Sampling Transisi Grade", "01", "01/09/2024") + """
## 1. Tujuan
Memastikan produk awal setelah ganti grade tidak tercampur grade sebelumnya.

## 2. Plant 1 dan Plant 2
Setelah ganti grade, sampel titik 1 dari mix pertama grade baru wajib dicek sensory dengan perhatian khusus pada rasa campur. Di gudang, 2 pallet terakhir grade lama dan 4 pallet pertama grade baru dicek ulang sampai pass.

## 3. Line Retail
Karena volume per mix kecil, transisi di Line Retail dicek per menit. Sampel pertama diambil sekitar menit ke-1 setelah produk grade baru keluar, lalu tiap menit sampai 2 sampel berturut-turut pass, maksimal 12 sampel. Yang dicatat adalah jam sampel diambil, tidak ada pencatatan resmi jam mulai transisi. Sampel yang belum pass disisihkan dan dicampur bertahap ke produk pass, maksimal 5 % per mix.

## 4. Catatan
Berdasarkan pengalaman, transisi dari susu (MLK-RT) ke krimer (CRM-RT) biasanya butuh lebih lama dibanding arah sebaliknya karena rasa milky lebih mudah terdeteksi.
"""


def spec_doc(grade, rev, valid_from, overrides=None, note=""):
    p = C.PRODUCTS[grade]
    s = dict(p["spec"])
    if overrides:
        s.update(overrides)
    lines = [l for l, c in C.LINES.items() if grade in c["grades"]]
    status = "Berlaku"
    for r in C.SPEC_REVISIONS:
        if r["grade"] == grade and rev == "A":
            status = f"Tidak berlaku, digantikan Rev {r['rev']} per {r['effective']:%d/%m/%Y}"
    coffee = "Wajib, hasil Pass (tidak feathering)" if p["coffee_test"] else "Tidak wajib"
    oil = C.MATERIALS[p["oil"]]["name"]
    prot = C.MATERIALS[p["protein_src"]]["name"]
    txt = header(f"SPEC-{grade}", f"Spesifikasi Produk {grade} ({p['name']})", rev, valid_from,
                 disusun="Tim RND", status=status)
    return txt + _spec_body(grade, p, s, lines, coffee, oil, prot, note)


def _spec_body(grade, p, s, lines, coffee, oil, prot, note):
    def f(x, nd=1):
        return f"{x:.{nd}f}".replace(".", ",")
    body = f"""
## Identitas produk
Kode grade {p['code']}, segmen {p['segment']}, diproduksi di {' dan '.join(C.LINES[l]['name'] for l in lines)}. Minyak dasar {oil}, sumber protein {prot}. Kemasan {'karung 25 kg' if p['segment'] == 'B2B' else 'karton isi 10 kg (sachet)'}.

Nomor batch: YYMMDD + kode grade + kode line, contoh {C.START_DATE:%y%m%d}{p['code']}{lines[0]}. Kode line P1 untuk Plant 1, P2 untuk Plant 2, RT untuk Line Retail.

## Spesifikasi release

| Parameter | Target | Batas |
|---|---|---|
| Lemak (%) | {f(p['fat'])} | {f(s['fat'][0])} sampai {f(s['fat'][1])} |
| Protein (%) | {f(p['protein'])} | min {f(s['protein_min'])} |
| Kadar air (%) | {f(p['moisture'])} | maks {f(s['moisture_max'])} |
| Viskositas larutan 20 % (cP) | {f(p['visc_base'])} | {f(s['visc'][0])} sampai {f(s['visc'][1])} |
| Bulk density (g/ml) | {f(p['bulk'], 2)} | {f(s['bulk'][0], 2)} sampai {f(s['bulk'][1], 2)} |
| Indeks kelarutan (ml) | | maks {f(s['solub_max'])} |
| Wettability (detik) | | maks {s['wett_max']} |
| Warna L* | | min {f(s['L_min'])} |
| pH larutan | {f(p['ph'])} | {f(s['ph'][0])} sampai {f(s['ph'][1])} |
| Coffee test | | {coffee} |
| TPC (cfu/g) | | maks {s['tpc_max']:,} |
| Kapang khamir (cfu/g) | | maks {s['ym_max']} |
| Coliform (cfu/g) | | kurang dari 10 |
| E. coli | | negatif |
| Salmonella | | negatif per 25 g |
| Sensory | | Pass atau TP1 terhadap kontrol |

Masa pakai kontrol sensory {p['control_days']} hari.
""".replace(f"{s['tpc_max']:,}", f"{s['tpc_max']:,}".replace(",", "."))
    if note:
        body += f"\n## Catatan revisi\n{note}\n"
    return body


def spec_docs():
    docs = {}
    for g in C.PRODUCTS:
        docs[f"spec/SPEC-{g}_RevA.md"] = spec_doc(g, "A", "01/07/2024")
    for r in C.SPEC_REVISIONS:
        docs[f"spec/SPEC-{r['grade']}_Rev{r['rev']}.md"] = spec_doc(
            r["grade"], r["rev"], f"{r['effective']:%d/%m/%Y}", overrides={r["param"]: r["new"]},
            note=(f"Batas kadar air diturunkan dari {str(r['old']).replace('.', ',')} % menjadi "
                  f"{str(r['new']).replace('.', ',')} % atas permintaan customer B2B (PT Kopi Instan Sejahtera) "
                  "karena keluhan caking di musim hujan. Parameter lain tidak berubah."))
    return docs


def sop_docs():
    return {
        "sop/SOP-QC-001_Penerimaan_Bahan_Baku_Rev03.md": SOP_RM,
        "sop/SOP-QC-005_Uji_Sensory_Produk_Jadi_Rev02.md": SOP_SENS_02,
        "sop/SOP-QC-005_Uji_Sensory_Produk_Jadi_Rev03.md": SOP_SENS_03,
        "sop/SOP-QC-007_Viskositas_dan_Brix_Rev01.md": SOP_VISC,
        "sop/SOP-QC-009_Analisa_NIRS_Serbuk_Rev02.md": SOP_NIRS,
        "sop/SOP-QC-015_Sampling_Transisi_Grade_Rev01.md": SOP_TRANS,
        **hold_sops(),
    }
