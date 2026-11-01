# Text documents for the RAG project. Static SOPs and specs come from doc_sop.py,
# everything else is written from the simulated data and the incidents drawn for this seed:
# NCRs, memos, complaint investigations, shift logbooks and monthly QC meeting notes.
# Numbers inside the documents come from the data, so a RAG answer can be checked against SQL.
#
# Documents only know what people knew at the time they were written. An NCR written in the
# middle of an incident can blame the wrong cause, and the real cause shows up in a later memo.
# SPOILER: this file reads the drawn incidents, so it is part of the answer key.

from datetime import date, timedelta

import numpy as np
import pandas as pd

import config as C
import doc_sop
from mess import typo
from outbound import QA_MGR, QC_SPV
from simulate import LINE_PROCESS, get_event

BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember"]
SENS_REV03 = C.VERIF_SHARE[1][0]  # SOP-QC-005 Rev 03, with the 14 day limit on control extension
CREAMERS = [g for g, p in C.PRODUCTS.items() if p["protein_src"] == "RM-CAS"]

# filled while writing, read by later sections
REF = {}    # memo numbers by key
NOTES = {}  # which symptom notes made it into the meeting minutes


def id_num(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def pct(x):
    return f"{100 * x:.1f}".replace(".", ",") + " %"


def tgl(d):
    return f"{pd.Timestamp(d):%d/%m/%Y}"


def ribu(n):
    return f"{int(n):,}".replace(",", ".")


def bln(d):
    d = pd.Timestamp(d)
    return f"{BULAN[d.month - 1]} {d.year}"


def kira(d):
    # how people actually say a date they only roughly remember
    d = pd.Timestamp(d)
    part = "awal" if d.day <= 10 else ("pertengahan" if d.day <= 20 else "akhir")
    return f"{part} {BULAN[d.month - 1]} {d.year}"


def lname(line):
    return C.LINES[line]["name"]


def sup_name(sid):
    return C.SUPPLIERS[sid]["name"]


def ev(kind):
    return get_event(kind)


def drawn(kind):
    return get_event(kind)["drawn"]


def period(d):
    return pd.Period(pd.Timestamp(d), "M")


def month_of_notice(d, min_days=7):
    # an incident starting in the last days of a month gets discussed the month after
    p = period(d)
    return p + 1 if p.end_time.day - pd.Timestamp(d).day < min_days else p


# 1. Memos (written when someone found out)

def memos(clean, truth, rng):
    items = []

    def add(key, prefix, d, slug, title, frm, to, body):
        if d <= C.END_DATE:
            items.append(dict(key=key, prefix=prefix, d=d, slug=slug, title=title, frm=frm, to=to, body=body.strip()))

    e = ev("spray_dryer_sensor_bias")
    if e["drawn"]:
        L, b = lname(e["line"]), e["magnitude"]
        base = LINE_PROCESS[e["line"]]["outlet"]
        add("dryer", "QC", e["end"], f"Bias_Sensor_Outlet_{e['line']}", f"Temuan Bias Sensor Suhu Outlet Spray Dryer {L}",
            "QC Supervisor dan Engineering", "QA Manager, Produksi, PPIC", f"""
Saat kalibrasi rutin tanggal {tgl(e['end'])}, sensor suhu outlet TT-102 di spray dryer {L} terbaca sekitar {id_num(b)} C lebih rendah dibanding termometer referensi. Dari tren logger, inlet {L} naik sekitar {id_num(1.35 * b, 0)} C sejak {kira(e['start'])} sementara outlet tetap terbaca {id_num(base, 0)} C. Artinya operator menaikkan inlet untuk mengejar angka outlet yang sebenarnya sudah tercapai, dan suhu outlet aktual berjalan sekitar {id_num(base + b, 0)} C.

Dampak yang terlihat di data QC {L} periode {tgl(e['start'])} sampai {tgl(e['end'])}: kadar air cenderung lebih rendah, warna L* turun, dan indeks kelarutan naik. Kalau suhunya cukup tinggi, muncul juga temuan sensory TP3 dengan catatan gosong.

Tindakan: sensor TT-102 sudah diganti, kalibrasi sensor suhu dryer dijadwalkan bulanan, dan NCR terkait {L} periode tersebut ditutup dengan root cause ini.
""")
    e = ev("viscometer_drift")
    if e["drawn"]:
        add("visc", "QC", e["end"], "Kalibrasi_Viskometer", "Hasil Kalibrasi Eksternal Viskometer Lab KimFis", "QC Supervisor",
            "Seluruh analis KimFis, QA Manager", f"""
Kalibrasi eksternal viskometer rotasi lab KimFis tanggal {tgl(e['end'])} menemukan pembacaan lebih tinggi sekitar {round(100 * e['magnitude'])} % dibanding standar. Pergeseran diperkirakan mulai {kira(e['start'])} dan bertambah sedikit demi sedikit.

Cek harian dengan cairan standar 5,0 cP sesuai SOP-QC-007 tidak berjalan sejak {kira(e['start'] - timedelta(days=5))} karena stok standar habis dan pemesanan ulang terlambat. Kenaikan viskositas sempat dibahas di rapat QC tapi dianggap variasi bahan baku.

Tindakan: viskometer sudah dikalibrasi ulang dan standar baru tersedia. Data viskositas {tgl(e['start'])} sampai {tgl(e['end'] - timedelta(days=1))} tidak dikoreksi mundur, jangan dipakai untuk analisa tren tanpa koreksi. Cek harian dengan standar wajib dicatat di logbook mulai hari ini.
""")
    e = ev("bad_oil_lot")
    if e["drawn"]:
        rec = clean["rm_receiving"]
        rd = pd.to_datetime(rec["received_at"]).dt.date
        bad = rec[(rec["material_code"] == e["material"]) & (rec["supplier_id"] == e["supplier"]) & (rd >= e["start"])
                  & (rd < e["end"]) & (rec["decision"] == "Conditional")]
        lots = ", ".join(f"{r.internal_lot} (PV {id_num(r.qc_pv, 2)})" for r in bad.itertuples()) or "beberapa lot"
        mat, sup = C.MATERIALS[e["material"]]["name"], sup_name(e["supplier"])
        add("oil", "QC", e["end"] + timedelta(days=1), "Lot_Minyak_Conditional", f"Lot {mat} Conditional dari {sup}",
            "QC Bahan Baku", "PPIC, Produksi, QC Supervisor", f"""
Beberapa kedatangan {mat} dari {sup} pada {tgl(e['start'])} sampai {tgl(e['end'] - timedelta(days=1))} masuk kategori Conditional karena PV mendekati batas: {lots}. Semua lot masih di bawah batas 2,0 meq/kg sehingga boleh dipakai dengan catatan pakai segera.

Mohon PPIC memprioritaskan lot ini dan QC produk jadi memperhatikan kemungkinan aroma tengik atau oily pada grade yang memakai {mat} ({e['grade']}). Supplier sudah diminta penjelasan.
""")
    e = ev("silent_supplier_change")
    if e["drawn"]:
        mat = C.MATERIALS[e["material"]]["name"]
        old = " dan ".join(sup_name(s) for s in e["old_supplier"].split(", "))
        use = "semua grade krimer" if e["material"] == "RM-CAS" else "grade susu"
        add("supplier", "RND", e["memo_date"], "Perubahan_Supplier", f"Perubahan Supplier {mat}", "RND",
            "Purchasing, PPIC, Produksi", f"""
Terhitung sejak {tgl(e['start'])}, {mat.lower()} untuk {use} ({e['grade']}) dipasok oleh {sup_name(e['new_supplier'])} menggantikan {old}. Alasan perubahan adalah harga dan kepastian pasokan.

Spesifikasi COA supplier baru memenuhi SOP-QC-001. Trial skala lab RND tidak menunjukkan perbedaan berarti pada viskositas larutan. Trial skala produksi belum dilakukan.

Formula tidak berubah, hanya sumber bahan.
""")
    e = ev("nirs_lamp_change")
    if e["drawn"]:
        add("lamp", "QC", e["start"], "Ganti_Lampu_NIRS", "Penggantian Lampu NIRS DS-01", "QC Supervisor", "Analis KimFis", f"""
Lampu NIRS DS-01 diganti tanggal {tgl(e['start'])} karena energi lampu sudah di bawah batas. Sesuai SOP-QC-009 perlu cek bias dengan minimal 10 sampel referensi, dijadwalkan minggu depan. Sementara itu hasil NIRS tetap dipakai untuk monitoring.
""")
        weeks = round((e["fix_date"] - e["start"]).days / 7)
        add("lamp_fix", "QC", e["fix_date"], "Koreksi_Bias_NIRS", "Koreksi Bias Model NIRS Setelah Ganti Lampu", "QC Supervisor",
            "Analis KimFis, QA Manager", f"""
Cek bias dengan 12 sampel referensi menunjukkan prediksi kadar air NIRS lebih tinggi rata-rata {id_num(e['bias'], 2)} % dibanding moisture analyzer sejak lampu diganti {tgl(e['start'])}. Lemak dan protein tidak menunjukkan bias berarti. Model kadar air semua grade sudah dikoreksi per {tgl(e['fix_date'])}.

Catatan: cek bias seharusnya dilakukan segera setelah ganti lampu, tertunda sekitar {weeks} minggu karena sampel referensi belum dikumpulkan.
""")
    e = ev("homogenizer_wear")
    if e["drawn"]:
        L = lname(e["line"])
        add("homog", "ENG", e["end"], f"Overhaul_Homogenizer_{e['line']}", f"Overhaul Homogenizer {L}", "Engineering",
            "Produksi, QC, PPIC", f"""
Overhaul homogenizer {L} tanggal {tgl(e['end'])} menemukan valve dan seat tahap pertama aus. Gauge tekanan masih terbaca dekat setpoint (sedikit turun beberapa bar), tapi efisiensi homogenisasi sudah menurun. Dari catatan operator, bunyi tidak normal mulai terdengar {kira(e['start'] + timedelta(days=10))}.

Valve dan seat sudah diganti. Disarankan penggantian preventif tiap 6 bulan dan pengecekan ukuran globula lemak oleh QC setelah maintenance.
""")
    e = ev("cip_failure")
    if e["drawn"]:
        L = lname(e["line"])
        rev = (" dan SOP-QC-012 direvisi untuk membatasi release urgent" if C.SOP_HOLD_REV05_DATE <= C.END_DATE else "")
        add("cip", "QC", e["end"], f"CIP_{e['line']}", f"CIP {L} Tidak Sempurna", "QC Supervisor", "QA Manager, Produksi, PPIC", f"""
Valve CIP {L} bermasalah sejak {tgl(e['start'])} sehingga siklus CIP tidak tuntas. Hasil mikro batch {L} periode {tgl(e['start'])} sampai {tgl(e['end'] - timedelta(days=1))} menunjukkan TPC jauh di atas biasanya. Batch dengan hasil TMS di-reject, dan mix yang sudah keluar lewat release urgent ditarik dari customer.

Tindakan: valve diganti, verifikasi CIP dengan swab ATP setelah setiap CIP selama 1 bulan{rev}.
""")
    e = ev("control_overdue")
    if e["drawn"]:
        ctrl = clean["sensory_controls"]
        ext = ctrl[(ctrl["grade"] == e["grade"]) & ctrl["extended"] & (pd.to_datetime(ctrl["end_use"]).dt.date == e["end"])]
        if len(ext):
            cid, due = ext["control_id"].iloc[0], pd.Timestamp(ext["due_date"].iloc[0]).date()
            rule = (f"Kontrol lama diperpanjang 14 hari sampai {tgl(due + timedelta(days=14))} sesuai SOP-QC-005 Rev 03."
                    if due >= SENS_REV03 else "Kontrol lama diperpanjang sampai kontrol baru siap, sesuai SOP-QC-005 Rev 02.")
            add("control", "QC", due, f"Perpanjangan_Kontrol_{e['grade'].replace('-', '')}",
                f"Perpanjangan Kontrol Sensory {e['grade']}", "QC Supervisor", "Analis KimFis, Verifikator", f"""
Kontrol {cid} untuk {e['grade']} jatuh tempo {tgl(due)}. Kandidat kontrol baru belum ada yang disetujui verifikator. {rule} Verifikator diminta menyiapkan kandidat kontrol baru dari produksi minggu ini.
""")

    # memo numbers run per department per year, with gaps for memos about other things
    items.sort(key=lambda x: x["d"])
    counter, docs = {}, {}
    for it in items:
        k = (it["prefix"], it["d"].year)
        counter[k] = counter.get(k, int(rng.integers(1, 6))) + int(rng.integers(1, 5))
        no = f"MEMO-{it['prefix']}-{it['d'].year}-{counter[k]:03d}"
        REF[it["key"]] = no
        docs[f"memo/{no}_{it['slug']}.md"] = (
            f"# {it['title']}\n\n| | |\n|---|---|\n| No. Memo | {no} |\n| Tanggal | {tgl(it['d'])} |\n"
            f"| Dari | {it['frm']} |\n| Kepada | {it['to']} |\n\n{it['body']}\n")
    return docs


# 2. NCRs

NCR_TMPL = """# Laporan Ketidaksesuaian (NCR)

| | |
|---|---|
| No. NCR | {no} |
| Tanggal | {date} |
| Area | {area} |
| Produk / Bahan | {product} |
| Batch / Lot terkait | {refs} |
| Dibuat oleh | {by} |
| Status | {status} |

## Deskripsi ketidaksesuaian
{desc}

## Tindakan segera
{action}

## Analisa penyebab
{cause}

## Tindakan perbaikan
{capa}
{closing}"""


def coffee_causes(m, line):
    # real reasons behind a month of coffee test failures on one line, and when QC learned each one
    out = []
    lo, hi = m.start_time.date(), m.end_time.date()
    e = ev("silent_supplier_change")
    if e["drawn"] and e["material"] == "RM-CAS" and e["start"] <= hi:
        out.append((f"perubahan supplier sodium caseinate ke {sup_name(e['new_supplier'])} per {tgl(e['start'])}"
                    f" ({REF.get('supplier', 'memo RND')}) yang tidak diinformasikan ke QC", e["known"]))
    e = ev("homogenizer_wear")
    if e["drawn"] and e["line"] == line and e["start"] <= hi and e["end"] > lo:
        out.append((f"keausan homogenizer {lname(line)} {kira(e['start'])} sampai {tgl(e['end'])} ({REF.get('homog', 'memo Engineering')})",
                    e["end"]))
    return out


def ncrs(clean, truth, rng):
    out = []
    rec = clean["rm_receiving"]
    for r in rec[rec["decision"] == "Reject"].itertuples():
        d = pd.Timestamp(r.received_at).date()
        if d < C.START_DATE:
            continue
        out.append(dict(date=d, area="QC Bahan Baku", product=r.material_name, refs=f"{r.internal_lot} (lot supplier {r.supplier_lot})",
                        desc=f"Kedatangan {r.material_name} dari {r.supplier_name} tanggal {tgl(d)} tidak memenuhi spesifikasi: {r.remarks}.",
                        action="Lot ditolak dan dikembalikan ke supplier, gudang diinformasikan supaya lot tidak masuk area release.",
                        cause="Ketidaksesuaian dari sisi supplier, menunggu penjelasan tertulis.",
                        capa="Supplier diminta corrective action report. Frekuensi uji untuk 3 kedatangan berikutnya dinaikkan.",
                        status="Closed", closing=f"\nDitutup {tgl(d + timedelta(days=14))} setelah supplier mengirim penjelasan.\n"))

    hist = clean["release_history"].copy()
    hist["d"] = pd.to_datetime(hist["status_time"]).dt.date
    kim = clean["sensory_kimfis"].copy()
    kim["mix_id"] = kim["sample_uid"].str[:-1]
    off = kim[kim["off_flavor"]].groupby("mix_id")["off_flavor_type"].agg(lambda s: s.value_counts().index[0])
    rej = hist[(hist["status"] == "REJECT") & hist["reason"].str.contains("off-flavor")].copy()
    rej["type"] = rej["mix_id"].map(off)
    rej["week"] = pd.to_datetime(rej["d"]).dt.to_period("W")
    e_dry, e_oil = ev("spray_dryer_sensor_bias"), ev("bad_oil_lot")
    oil_grades = (e_oil["grade"] or "").split(", ")
    NOTES["burnt_ncr"] = False
    for (week, line, typ), g in rej.groupby(["week", "line", "type"]):
        if len(g) < 2:
            continue
        d = g["d"].min()
        refs = ", ".join(sorted(g["mix_id"].str.replace("-", " mix ", regex=False))[:12]) + (" dan lainnya" if len(g) > 12 else "")
        grades = ", ".join(sorted(g["grade"].unique()))
        word = {"oxid": "tengik/oily", "burnt": "gosong", "mixgrade": "rasa campur", "random": "aroma asing"}.get(typ, typ)
        desc = (f"{len(g)} mix di {lname(line)} ({grades}) minggu {week.start_time:%d/%m/%Y} di-reject karena "
                f"off-flavor {word} yang dikonfirmasi verifikator.")
        closing = ""
        if typ == "burnt" and line == e_dry["line"] and e_dry["start"] <= d < e_dry["end"] + timedelta(days=3):
            NOTES["burnt_ncr"] = True
            cause = (f"Dalam investigasi. Suhu outlet di logger {lname(line)} normal. Dugaan sementara "
                     "nozzle atomizer aus atau ada deposit di chamber.")
            capa = "Engineering cek nozzle dan bersihkan chamber. QC naikkan perhatian pada titik sampel 2 dan 3."
            closing = (f"\nCatatan penutupan {tgl(e_dry['end'] + timedelta(days=2))}: root cause sebenarnya adalah bias "
                       f"sensor outlet TT-102 sekitar {id_num(e_dry['magnitude'])} C lebih rendah ({REF.get('dryer', 'memo QC')}). "
                       "Nozzle dalam kondisi normal.\n")
        elif typ == "oxid" and e_oil["start"] <= d < e_oil["end"] + timedelta(days=21) and set(g["grade"]) & set(oil_grades):
            cause = (f"Mix yang terdampak memakai lot {C.MATERIALS[e_oil['material']]['name']} Conditional dari "
                     f"{sup_name(e_oil['supplier'])} dengan PV mendekati batas ({REF.get('oil', 'memo QC Bahan Baku')}).")
            capa = ("Lot minyak Conditional dengan PV 1,5 atau lebih tidak dipakai lagi tanpa uji sensory minyak. "
                    "Supplier diminta perbaikan penanganan transport.")
        elif typ == "mixgrade":
            cause = "Sisa produk grade sebelumnya di jalur setelah ganti grade, waktu flushing kurang."
            capa = "Tambah waktu flushing 5 menit setelah ganti grade dan cek titik 1 mix pertama lebih ketat."
        else:
            cause = "Kasus sporadis, tidak ditemukan pola dari data proses dan bahan baku."
            capa = "Monitoring lanjutan."
        out.append(dict(date=d, area=lname(line), product=grades, refs=refs, desc=desc,
                        action="Mix di-reject dan dipisahkan di gudang reject. Sampel retain disimpan untuk investigasi.",
                        cause=cause, capa=capa, status="Closed", closing=closing))

    lab = clean["qc_lab_kimfis"]
    ct = lab[lab["coffee_test"].notna()].copy()
    ct["m"] = pd.to_datetime(ct["prod_date"]).dt.to_period("M")
    rates = ct.groupby(["m", "line"]).agg(n=("coffee_test", "size"), fail=("coffee_test", lambda s: (s == "Fail").sum()))
    rates["rate"] = rates["fail"] / rates["n"]
    NOTES["coffee"] = []
    for (m, line), r in rates.iterrows():
        if r["rate"] < 0.10 or r["n"] < 10:
            continue
        d = (m.end_time + pd.Timedelta(days=2)).date()
        desc = (f"Coffee test gagal (feathering) di {lname(line)} bulan {m.strftime('%m/%Y')} sebanyak "
                f"{int(r['fail'])} dari {int(r['n'])} sampel ({pct(r['rate'])}). Normalnya di bawah 3 %.")
        causes = coffee_causes(m, line)
        known = max((k for _, k in causes), default=None)
        closing, status = "", "Open"
        if causes and known <= d:
            cause = "Terkait " + ", ditambah ".join(t for t, _ in causes) + "."
            status = "Closed"
        else:
            cause = "Penyebab belum diketahui. pH larutan dan tekanan homogenizer di log produksi masih dalam range normal."
            eh = ev("homogenizer_wear")
            if eh["drawn"] and eh["line"] == line and eh["start"] + timedelta(days=10) <= d:
                cause += f" Dugaan sementara homogenizer {lname(line)}, operator melaporkan bunyi tidak normal."
            if causes and known <= C.END_DATE:
                closing = (f"\nCatatan penutupan {tgl(known + timedelta(days=3))}: kenaikan coffee test gagal ini terkait "
                           + ", ditambah ".join(t for t, _ in causes) + ".\n")
                status = "Closed"
        if causes and status == "Closed":
            NOTES["coffee"].append(dict(m=m, line=line, rate=r["rate"], causes=[t for t, _ in causes]))
        out.append(dict(date=d, area=lname(line), product="Grade krimer dengan coffee test", refs=f"produksi {m.strftime('%m/%Y')}",
                        desc=desc, action="Mix dengan coffee test gagal di-hold dan di-blending ke mix yang pass.",
                        cause=cause, capa="RND dan QC evaluasi stabilitas emulsi. Coffee test dilakukan di semua titik sampel sementara waktu.",
                        status=status, closing=closing))

    mic = clean["micro_results"]
    bad = mic[mic["micro_status"] == "Fail"].copy()
    e_cip = ev("cip_failure")
    pdate = pd.to_datetime(bad["prod_date"]).dt.date
    cip = bad[(bad["line"] == e_cip["line"]) & (pdate >= e_cip["start"]) & (pdate < e_cip["end"])]
    if len(cip):
        L = lname(e_cip["line"])
        rev = ", revisi SOP-QC-012 (Rev 05)" if C.SOP_HOLD_REV05_DATE <= C.END_DATE else ""
        out.append(dict(date=pd.Timestamp(cip["result_date"].min()).date(), area=L, product=", ".join(sorted(cip["grade"].unique())),
                        refs=", ".join(cip["batch_no"]),
                        desc=f"{len(cip)} batch {L} produksi {tgl(e_cip['start'])} sampai {tgl(e_cip['end'] - timedelta(days=1))} hasil mikro TMS, "
                             f"TPC tertinggi {ribu(cip['tpc_cfu_g'].max())} cfu/g.",
                        action="Batch di-reject. Mix yang sudah keluar dengan release urgent di-recall.",
                        cause=f"CIP {L} tidak tuntas karena valve CIP bermasalah ({REF.get('cip', 'memo QC')}).",
                        capa=f"Ganti valve, verifikasi ATP setelah CIP{rev}.", status="Closed",
                        closing=f"\nDitutup {tgl(e_cip['end'] + timedelta(days=14))}.\n"))
    for r in bad.drop(cip.index).itertuples():
        out.append(dict(date=pd.Timestamp(r.result_date).date(), area=lname(r.line), product=r.grade, refs=r.batch_no,
                        desc=f"Hasil mikro batch {r.batch_no} TMS ({r.fail_reason}).",
                        action="Batch di-hold lalu di-reject.", cause="Tidak ditemukan penyebab spesifik, kasus tunggal.",
                        capa="Swab lingkungan area packing dan verifikasi CIP.", status="Closed", closing=""))

    e = ev("viscometer_drift")
    if e["drawn"] and e["end"] <= C.END_DATE:
        out.append(dict(date=e["end"], area="Lab KimFis", product="Semua grade",
                        refs=f"data viskositas {kira(e['start'])} sampai {tgl(e['end'])}",
                        desc=f"Viskometer lab terbaca lebih tinggi sekitar {round(100 * e['magnitude'])} % saat kalibrasi eksternal.",
                        action="Alat dikalibrasi ulang, standar 5,0 cP dipesan ulang.",
                        cause=f"Cek harian dengan standar tidak dilakukan karena standar habis ({REF.get('visc', 'memo QC')}).",
                        capa="Stok minimum standar ditetapkan 2 botol, cek harian wajib dicatat.", status="Closed", closing=""))

    cmp = clean["complaints"]
    for r in cmp[cmp["justified"] & (cmp["status"] == "Closed")].itertuples():
        out.append(dict(date=pd.Timestamp(r.received_date).date() + timedelta(days=3), area="Komplain customer", product=r.grade,
                        refs=f"{r.batch_no}, {r.complaint_id}",
                        desc=f"Komplain {r.customer_name}: {r.description.lower()}.",
                        action="Sampel retain diuji ulang, customer diberi penggantian sesuai qty terdampak.",
                        cause=f"Lihat laporan investigasi {r.complaint_id}.", capa="Sesuai laporan investigasi.",
                        status="Closed", closing=""))

    out = [o for o in out if o["date"] <= C.END_DATE]
    out.sort(key=lambda x: x["date"])
    docs, counters = {}, {}
    for o in out:
        yy = f"{o['date']:%y}"
        counters[yy] = counters.get(yy, 0) + 1
        no = f"NCR-{yy}-{counters[yy]:03d}"
        o["no"] = no
        txt = NCR_TMPL.format(no=no, date=tgl(o["date"]), area=o["area"], product=o["product"], refs=o["refs"],
                              by=str(rng.choice(["Agus Salim", "Dewi Lestari", "Andi Prasetyo", "Yusuf Hidayat"])),
                              status=o["status"], desc=o["desc"], action=o["action"], cause=o["cause"], capa=o["capa"],
                              closing=o["closing"])
        docs[f"ncr/{no}.md"] = txt
    return docs, out


# 3. Complaint investigations

CAUSE_TEXT = {
    "Off-flavor tengik": ("Sampel retain diuji verifikator, terdeteksi aroma tengik.",
                          "Oksidasi minyak, batch memakai lot minyak dengan PV mendekati batas."),
    "Feathering di kopi": ("Coffee test ulang sampel retain: feathering terjadi.",
                           "Stabilitas emulsi rendah di aplikasi kopi panas."),
    "Caking / menggumpal": ("Kadar air sampel retain mendekati batas maksimal.",
                            "Kadar air tinggi ditambah kelembaban udara musim hujan saat penyimpanan."),
    "Bintik hitam": ("Ditemukan partikel gosong pada sampel retain.", "Suhu outlet dryer terlalu tinggi saat produksi."),
    "Kurang creamy": ("Sampel retain dinilai verifikator agak kurang creamy terhadap kontrol.",
                      "Body produk lebih rendah dari biasanya."),
    "Mikro": ("Hasil mikro internal batch tersebut juga TMS.", "Kontaminasi mikro di jalur produksi."),
    "Kemasan / lain-lain": ("Pengecekan gudang dan sampel retain.", "Penanganan kemasan saat distribusi."),
}


def investigations(clean, rng):
    cmp, lab, hist = clean["complaints"], clean["qc_lab_kimfis"], clean["release_history"]
    kim = clean["sensory_kimfis"]
    docs = {}
    for r in cmp.itertuples():
        lb = lab[lab["batch_no"] == r.batch_no]
        kb = kim[kim["batch_no"] == r.batch_no]
        hb = hist[hist["batch_no"] == r.batch_no]
        rel = hb.sort_values("status_time").groupby("mix_id")["status"].last().value_counts().to_dict()
        rel_txt = ", ".join(f"{k} {v} mix" for k, v in rel.items())
        grades = kb["grade_result"].value_counts().to_dict()
        g_txt = ", ".join(f"{k} {v}" for k, v in grades.items())
        finding, cause = CAUSE_TEXT[r.category]
        if r.status == "Open":
            concl = "Investigasi masih berjalan."
        elif r.justified:
            concl = f"Komplain terbukti. {cause}"
        else:
            concl = "Komplain tidak terbukti. Sampel retain dan data batch dalam batas normal."
            finding = "Sampel retain diuji ulang dan tidak ditemukan penyimpangan."
        ct = lb["coffee_test"].dropna()
        ct_txt = f", coffee test gagal {int((ct == 'Fail').sum())} dari {len(ct)}" if len(ct) else ""
        txt = f"""# Laporan Investigasi Komplain {r.complaint_id}

| | |
|---|---|
| Tanggal terima | {tgl(r.received_date)} |
| Customer | {r.customer_name} |
| Produk | {r.grade} |
| Batch | {r.batch_no} (DO {r.do_no}) |
| Kategori | {r.category} |
| Qty terdampak | {r.qty_affected_kg} kg |
| Status | {r.status} |

## Keluhan
{r.description}.

## Data batch
Kadar air rata-rata {id_num(lb['moisture_pct'].mean())} % (maks {id_num(lb['moisture_pct'].max())} %), viskositas rata-rata {id_num(lb['viscosity_cp'].mean())} cP{ct_txt}. Hasil sensory KimFis: {g_txt}. Status akhir mix: {rel_txt}.

## Temuan
{finding}

## Kesimpulan
{concl}
"""
        docs[f"complaints/INV-{r.complaint_id}.md"] = txt
    return docs


# 4. Shift logbooks (informal, one file per month)

ABBR = [("sudah", "sdh"), ("tidak", "tdk"), ("belum", "blm"), ("dengan", "dg"), ("yang", "yg"), ("untuk", "utk")]


def informal(s, rng):
    for a, b in ABBR:
        if a in s and rng.random() < 0.6:
            s = s.replace(a, b)
    return typo(s, rng)


def logbooks(clean, rng):
    kim = clean["sensory_kimfis"].copy()
    kim["tt"] = pd.to_datetime(kim["test_time"])
    kim["roster_day"] = (kim["tt"] - pd.to_timedelta((kim["tt"].dt.hour < 7).astype(int), unit="D")).dt.date
    kim["shift"] = np.select([kim["tt"].dt.hour.between(7, 14), kim["tt"].dt.hour.between(15, 22)], [1, 2], 3)
    trn = clean["retail_transition_samples"].copy()
    trn["st"] = pd.to_datetime(trn["sample_time"])
    names = {k: v["name"].split()[0] for k, v in C.KIMFIS_ANALYSTS.items()}
    lab = clean["qc_lab_kimfis"].copy()
    lab["tt"] = pd.to_datetime(lab["test_time"])
    lab_day = lab.groupby(lab["tt"].dt.date)["viscosity_cp"].mean()
    ev_v, ev_l, ev_h = ev("viscometer_drift"), ev("nirs_lamp_change"), ev("homogenizer_wear")
    lamp_fix = C.NIRS_BIAS_FIX_DATE

    books = {}
    for (day, sh), g in kim.groupby(["roster_day", "shift"]):
        notes = []
        for line, gl in g.groupby("line"):
            n_mix = gl["sample_uid"].str[:-1].nunique()
            grades = gl.groupby("grade")["sample_uid"].apply(lambda s: s.str[:-1].nunique())
            gtxt = ", ".join(f"{k} {v}" for k, v in grades.items())
            bad = gl[gl["grade_result"].isin(["TP2+", "TP2-", "TP3"])]
            tp1 = gl["grade_result"].str.startswith("TP1").sum()
            line_txt = f"{line}: {n_mix} mix ({gtxt})"
            if len(bad):
                items = [f"{r.sample_code} {r.batch_no} {r.grade_result} {r.notes}" for r in bad.itertuples()]
                line_txt += f". {' ; '.join(items)}, sudah lapor spv, mix hold"
            elif tp1:
                line_txt += f", TP1 {tp1} sampel"
            else:
                line_txt += ", aman"
            notes.append(line_txt)
        if sh == 1 or sh == 2:
            st = trn[(trn["st"].dt.date == day) & (trn["st"].dt.hour.between(7 if sh == 1 else 15, 14 if sh == 1 else 22))]
            for tid, gt in st.groupby("transition_id"):
                fails = (gt["result"] != "Pass").sum()
                notes.append(f"RT transisi {gt['from_grade'].iloc[0]} ke {gt['to_grade'].iloc[0]} jam {gt['st'].min():%H.%M}, "
                             f"{fails} sampel belum pass, total {len(gt)} sampel")
        extra = []
        if ev_v["drawn"] and ev_v["start"] + timedelta(days=20) <= day < ev_v["end"] and rng.random() < 0.06:
            v = lab_day.get(day, np.nan)
            extra.append(f"visko kok tinggi semua ya hari ini (rata2 {id_num(v)} cP), standar 5 cP masih kosong")
        if ev_l["drawn"] and ev_l["start"] <= day < lamp_fix and rng.random() < 0.08:
            extra.append("KA NIRS selisih sama moisture analyzer, NIRS lebih tinggi sedikit")
        if ev_l["drawn"] and day == ev_l["start"] and sh == 1:
            extra.append("lampu NIRS diganti hari ini")
        if ev_h["drawn"] and ev_h["start"] + timedelta(days=10) <= day < ev_h["end"] and rng.random() < 0.05:
            extra.append(f"info operator {ev_h['line']} homog bunyi")
        if rng.random() < 0.04:
            extra.append(str(rng.choice(["PPIC minta release cepat utk kiriman besok", "stok cawan NIRS tinggal sedikit",
                                         "AC lab mati 1 jam", "sampel retain rak 3 penuh", "kertas print habis"])))
        notable = any("hold" in n for n in notes) or extra or any("RT transisi" in n for n in notes)
        if not notable and rng.random() > 0.25:
            continue
        analyst = names[g["analyst_id"].mode().iloc[0]]
        body = "\n".join(f"- {informal(n, rng)}" for n in notes + extra)
        month = f"{day:%Y-%m}"
        books.setdefault(month, []).append(f"### {day:%d/%m/%Y} Shift {sh} ({analyst})\n{body}\n")
    docs = {}
    for month, entries in books.items():
        docs[f"logbook/Logbook_QC_{month}.md"] = (f"# Logbook Shift QC KimFis {month}\n\n"
                                                 "Catatan serah terima shift, ditulis analis yang bertugas.\n\n"
                                                 + "\n".join(entries))
    return docs


# 5. Monthly QC meeting notes

def meetings(clean, truth, ncr_list):
    kim = clean["sensory_kimfis"].copy()
    kim["m"] = pd.to_datetime(kim["prod_date"]).dt.to_period("M")
    kim["pd"] = pd.to_datetime(kim["prod_date"])
    ver = clean["sensory_verifikator"].copy()
    ver["m"] = pd.to_datetime(ver["prod_date"]).dt.to_period("M")
    lab = clean["qc_lab_kimfis"].copy()
    lab = lab[~lab["is_retest"]]
    lab["m"] = pd.to_datetime(lab["prod_date"]).dt.to_period("M")
    lab["pd"] = pd.to_datetime(lab["prod_date"])
    final = truth["final_status"].merge(clean["production_mix_log"][["mix_id", "prod_date", "line", "grade"]], on="mix_id")
    final["m"] = pd.to_datetime(final["prod_date"]).dt.to_period("M")
    hold_mix = clean["release_history"].query("status == 'HOLD'")["mix_id"].unique()
    final["held"] = final["mix_id"].isin(hold_mix)
    mic = clean["micro_results"].copy()
    mic["m"] = pd.to_datetime(mic["prod_date"]).dt.to_period("M")
    rec = clean["rm_receiving"].copy()
    rec["m"] = pd.to_datetime(rec["received_at"]).dt.to_period("M")
    cmp = clean["complaints"].copy()
    cmp["m"] = pd.to_datetime(cmp["received_date"]).dt.to_period("M")
    ncr = pd.DataFrame(ncr_list)
    ncr["m"] = pd.to_datetime(ncr["date"]).dt.to_period("M")

    def avg(df, col, lo, hi, **flt):
        x = df[(df["pd"] >= pd.Timestamp(lo)) & (df["pd"] < pd.Timestamp(hi))]
        for k, v in flt.items():
            x = x[x[k].isin(v if isinstance(v, list) else [v])]
        return x[col].mean() if len(x) else np.nan

    def rate(df, lo, hi, val, **flt):
        x = df[(df["pd"] >= pd.Timestamp(lo)) & (df["pd"] < pd.Timestamp(hi))]
        for k, v in flt.items():
            x = x[x[k].isin(v if isinstance(v, list) else [v])]
        return (x["grade_result"] == val).mean() if len(x) else np.nan

    E = {k: ev(k) for k in ("spray_dryer_sensor_bias", "viscometer_drift", "bad_oil_lot", "silent_supplier_change",
                            "nirs_lamp_change", "homogenizer_wear", "cip_failure", "control_overdue",
                            "silent_reformulation_costdown", "production_trial", "silent_reformulation_dkp")}
    NOTES["costdown"] = []
    docs = {}
    for m in sorted(kim["m"].unique()):
        k, f, l = kim[kim["m"] == m], final[final["m"] == m], lab[lab["m"] == m]
        if len(f) == 0:
            continue
        lo, hi = m.start_time, m.end_time + pd.Timedelta(days=1)
        meet = (m.end_time + pd.Timedelta(days=5)).date()
        while meet.weekday() >= 5:
            meet += timedelta(days=1)
        pass_rate = (k["grade_result"] == "Pass").mean()
        by_grade = k.groupby("grade")["grade_result"].apply(lambda s: (s == "Pass").mean())
        tp_dist = k["grade_result"].value_counts(normalize=True)
        v = ver[ver["m"] == m]
        agree = (v["grade_result"] == v["kimfis_grade"]).mean() if len(v) else np.nan
        ct = l["coffee_test"].dropna()
        ct_fail = (ct == "Fail").mean() if len(ct) else np.nan
        visc = l.groupby("grade")["viscosity_cp"].mean()
        st = f["final_status"].value_counts()
        mc, rc, cm, nc = mic[mic["m"] == m], rec[rec["m"] == m], cmp[cmp["m"] == m], ncr[ncr["m"] == m]
        grade_rows = "\n".join(f"| {g} | {pct(by_grade[g])} | {id_num(visc.get(g, np.nan))} |" for g in by_grade.index)
        cm_txt = ", ".join(f"{c} {n}" for c, n in cm["category"].value_counts().items()) or "tidak ada"
        items = []

        # what people knew at the time of this meeting
        e = E["spray_dryer_sensor_bias"]
        if e["drawn"] and m == month_of_notice(e["start"]):
            L, line = lname(e["line"]), e["line"]
            n3 = (k[k["line"] == line]["off_flavor_type"] == "burnt").sum()
            l_now = avg(lab, "L_star", max(lo, pd.Timestamp(e["start"])), hi, line=line)
            l_ref = avg(lab, "L_star", pd.Timestamp(e["start"]) - pd.Timedelta(days=60), pd.Timestamp(e["start"]), line=line)
            if n3 >= 3:
                items.append(f"TP3 dengan catatan gosong di {L} naik ({n3} sampel). Data suhu outlet di log produksi normal. "
                             f"Engineering diminta cek nozzle dan chamber. PIC: Produksi {line}.")
            elif l_ref - l_now > 0.2:
                items.append(f"Warna L* {L} rata-rata {id_num(l_now)} (dua bulan sebelumnya {id_num(l_ref)}), kadar air juga "
                             "cenderung lebih rendah. Data suhu outlet di log produksi normal, penyebab belum diketahui.")
        if e["drawn"] and m == period(e["end"]) and "dryer" in REF:
            items.append(f"Root cause temuan {lname(e['line'])} ketemu {tgl(e['end'])}: sensor outlet TT-102 bias sekitar "
                         f"{id_num(e['magnitude'])} C lebih rendah, sensor sudah diganti ({REF['dryer']}). Kalibrasi sensor dryer jadi bulanan.")
        e = E["viscometer_drift"]
        if e["drawn"] and period(e["start"]) < m < period(e["end"]):
            ref = avg(lab, "viscosity_cp", pd.Timestamp(e["start"]) - pd.Timedelta(days=90), pd.Timestamp(e["start"]))
            now = avg(lab, "viscosity_cp", lo, hi)
            if now / ref - 1 > 0.03:
                items.append(f"Viskositas rata-rata semua grade naik {id_num(100 * (now / ref - 1))} % dibanding tiga bulan "
                             "sebelumnya. Belum ada komplain. Dugaan variasi bahan baku, dipantau dulu.")
        if e["drawn"] and m == period(e["end"]) and "visc" in REF:
            items.append(f"Kalibrasi eksternal viskometer {tgl(e['end'])} menemukan pembacaan tinggi sekitar "
                         f"{round(100 * e['magnitude'])} %. Kenaikan viskositas sejak {kira(e['start'])} ternyata dari alat "
                         f"({REF['visc']}). Data periode itu jangan dipakai untuk tren.")
        e = E["bad_oil_lot"]
        if e["drawn"] and m == period(e["start"]):
            n3 = (k["off_flavor_type"] == "oxid").sum()
            mat, sup = C.MATERIALS[e["material"]]["name"], sup_name(e["supplier"])
            items.append(f"Lot {mat} Conditional dari {sup} dipakai sejak {kira(e['start'])}. TP3 tengik {n3} sampel bulan "
                         f"ini. Customer grade {e['grade']} perlu dipantau.")
        if e["drawn"] and period(e["start"]) < m <= period(e["start"]) + 2:
            n = (cm["category"] == "Off-flavor tengik").sum()
            if n:
                items.append(f"Komplain tengik masuk {n} kasus bulan ini, kemungkinan dari batch {bln(e['start'])} yang lolos.")
        a6 = C.KIMFIS_ANALYSTS["AN06"]
        if a6["start"] <= m.end_time.date() and m.start_time.date() < a6["training_until"] + timedelta(days=20):
            k6 = k[k["analyst_id"] == "AN06"]
            v6 = v[v["sample_uid"].isin(k6["sample_uid"])]
            ag6 = (v6["grade_result"] == v6["kimfis_grade"]).mean() if len(v6) else np.nan
            items.append(f"Analis baru Fitri (mulai {tgl(a6['start'])}) masih masa training, kesesuaian dengan verifikator "
                         f"{pct(ag6) if not np.isnan(ag6) else '-'} dibanding rata-rata {pct(agree)}. Lanjut pendampingan.")
        e = E["silent_supplier_change"]
        if e["drawn"]:
            known = period(e["known"])
            grades = e["grade"].split(", ")
            if period(e["start"]) <= m < known:
                b_lo, b_hi = pd.Timestamp(e["start"]) - pd.Timedelta(days=120), pd.Timestamp(e["start"]) - pd.Timedelta(days=15)
                dv = avg(lab, "viscosity_cp", max(lo, pd.Timestamp(e["start"])), hi, grade=grades) / avg(lab, "viscosity_cp", b_lo, b_hi, grade=grades) - 1
                tp_now = rate(kim, max(lo, pd.Timestamp(e["start"])), hi, "TP1-", grade=grades)
                tp_base = rate(kim, b_lo, b_hi, "TP1-", grade=grades)
                if dv < -0.02 or tp_now > 1.3 * tp_base:
                    extra = f", coffee test gagal {pct(ct_fail)}" if e["material"] == "RM-CAS" else ""
                    arah = f"naik {id_num(100 * dv)} %" if dv > 0 else f"turun {id_num(-100 * dv)} %"
                    items.append(f"Grade {e['grade']}: viskositas {arah} dibanding periode sebelumnya, TP1- "
                                 f"{pct(tp_now)} (biasanya {pct(tp_base)}){extra}. Penyebab belum diketahui, data proses "
                                 "di log produksi normal. RND bilang formula tidak berubah. PIC: QC dan RND.")
            if m == known and e["known"] <= C.END_DATE:
                memo = f"Memo RND tanggal {tgl(e['memo_date'])} hanya ke Purchasing, PPIC, Produksi. " if "supplier" in REF else ""
                items.append(f"Info dari Purchasing (obrolan, bukan memo): supplier {C.MATERIALS[e['material']]['name'].lower()} "
                             f"ganti ke {sup_name(e['new_supplier'])} sejak {tgl(e['start'])}. {memo}QC minta masuk "
                             "distribusi memo perubahan bahan baku dan minta COA kedua supplier untuk dibandingkan.")
        e = E["nirs_lamp_change"]
        if e["drawn"] and m == period(e["start"]):
            items.append(f"Lampu NIRS diganti {tgl(e['start'])}. Analis melaporkan KA NIRS lebih tinggi dari moisture analyzer. "
                         "Cek bias belum dilakukan, sampel referensi dikumpulkan dulu.")
        if e["drawn"] and m == period(e["fix_date"]) and "lamp_fix" in REF:
            weeks = round((e["fix_date"] - e["start"]).days / 7)
            items.append(f"Bias KA NIRS +{id_num(e['bias'], 2)} % dikoreksi {tgl(e['fix_date'])} ({REF['lamp_fix']}). "
                         f"Terlambat sekitar {weeks} minggu dari SOP.")
        for r in C.SPEC_REVISIONS:
            if m == period(r["effective"]):
                items.append(f"Spesifikasi {r['grade']} Rev {r['rev']} berlaku {tgl(r['effective'])}, batas kadar air jadi "
                             f"{id_num(r['new'])} % (sebelumnya {id_num(r['old'])} %).")
        if m == period(SENS_REV03):
            items.append(f"SOP-QC-005 Rev 03 berlaku {tgl(SENS_REV03)}: skala sensory pakai angka, ID kontrol wajib ditulis, verifikasi acak 30 %.")
        for a, b in C.SHUTDOWNS:
            if m == period(a):
                items.append(f"Shutdown Lebaran {tgl(a)} sampai {tgl(b)}, produksi pertama setelahnya dipantau lebih ketat.")
        e = E["homogenizer_wear"]
        if e["drawn"]:
            notice = e["start"] + timedelta(days=10)
            if notice < e["end"] and m == month_of_notice(notice, 3):
                L = lname(e["line"])
                tp = rate(kim, max(lo, pd.Timestamp(e["start"])), hi, "TP1-", line=e["line"])
                items.append(f"Creamy TP1- di {L} {pct(tp)} sampel. Operator {e['line']} lapor homogenizer bunyi. "
                             "Engineering jadwalkan overhaul.")
            if m == period(e["end"]) and "homog" in REF:
                items.append(f"Overhaul homogenizer {lname(e['line'])} {tgl(e['end'])}, valve dan seat aus ({REF['homog']}). "
                             f"Hasil sensory {e['line']} dipantau 2 minggu setelah overhaul.")
        e = E["cip_failure"]
        if e["drawn"] and m == period(e["start"]):
            nb = (mc["micro_status"] == "Fail").sum()
            nr = (f["final_status"] == "RECALL").sum()
            rev = " SOP-QC-012 direvisi." if C.SOP_HOLD_REV05_DATE <= C.END_DATE else ""
            items.append(f"CIP {lname(e['line'])} bermasalah {tgl(e['start'])} sampai {tgl(e['end'] - timedelta(days=1))}. "
                         f"{nb} batch mikro TMS, {nr} mix recall karena sudah keluar lewat release urgent "
                         f"({REF.get('cip', 'memo QC')}).{rev}")
        if C.SOP_HOLD_REV05_DATE <= C.END_DATE and m == period(C.SOP_HOLD_REV05_DATE):
            items.append(f"SOP-QC-012 Rev 05 berlaku {tgl(C.SOP_HOLD_REV05_DATE)}: release urgent tidak boleh untuk retail, "
                         "B2B wajib baca awal TPC 48 jam.")
        e = E["control_overdue"]
        if e["drawn"] and m == period(e["start"]):
            tp = rate(kim, max(lo, pd.Timestamp(e["start"])), hi, "TP1+", grade=e["grade"])
            items.append(f"Kontrol {e['grade']} diperpanjang sejak {tgl(e['start'])}, kandidat kontrol baru belum disetujui. "
                         f"TP1+ {e['grade']} {pct(tp)}. Action: verifikator siapkan kontrol baru minggu ini.")
        if e["drawn"] and m == period(e["end"]):
            limit = (" Total perpanjangan melebihi batas 14 hari di SOP-QC-005 Rev 03, dicatat sebagai temuan audit internal."
                     if e["start"] >= SENS_REV03 else "")
            items.append(f"Kontrol baru {e['grade']} akhirnya dipakai {tgl(e['end'])}.{limit}")

        # unannounced formula and process changes: QC sees the numbers, nobody has told them why
        e = E["silent_reformulation_costdown"]
        if e["drawn"] and period(e["start"]) <= m <= period(e["start"]) + 2 and len(NOTES["costdown"]) < 2:
            g = e["grade"]
            ref = avg(lab, "protein_pct", pd.Timestamp(e["start"]) - pd.Timedelta(days=75), pd.Timestamp(e["start"]) - pd.Timedelta(days=10), grade=g)
            now = avg(lab, "protein_pct", max(lo, pd.Timestamp(e["start"])), hi, grade=g)
            if ref - now > 0.035 * ref:
                follow = "Sudah ditanyakan ke RND, belum ada jawaban." if not NOTES["costdown"] else "RND belum memberi jawaban, dipantau terus."
                items.append(f"Protein {g} rata-rata {id_num(now, 2)} % (sebelumnya {id_num(ref, 2)} %), masih di atas batas "
                             f"minimal {id_num(C.PRODUCTS[g]['spec']['protein_min'])} %. {follow}")
                NOTES["costdown"].append(m)
        e = E["silent_reformulation_dkp"]
        if e["drawn"] and m == period(e["trial_note"]):
            items.append("RND info sedang trial penambahan dipotassium phosphate di krimer caseinate untuk stabilitas di kopi.")
        if e["drawn"] and period(e["start"]) <= m <= period(e["start"]) + 1:
            ref = avg(lab, "ph", pd.Timestamp(e["start"]) - pd.Timedelta(days=90), pd.Timestamp(e["start"]), grade=CREAMERS)
            now = avg(lab, "ph", max(lo, pd.Timestamp(e["start"])), hi, grade=CREAMERS)
            if now - ref > 0.05:
                items.append(f"pH grade krimer rata-rata {id_num(now, 2)} (tiga bulan sebelumnya {id_num(ref, 2)}), masih dalam "
                             f"spek. Coffee test gagal {pct(ct_fail)}. Penyebab perubahan pH belum diketahui.")
        e = E["production_trial"]
        if e["drawn"] and m == period(e["start"]):
            now = avg(lab, "moisture_pct", e["start"], e["end"], line=e["line"])
            ref = avg(lab, "moisture_pct", pd.Timestamp(e["start"]) - pd.Timedelta(days=28), pd.Timestamp(e["start"]), line=e["line"])
            if now - ref > 0.15:
                items.append(f"Kadar air {lname(e['line'])} minggu {tgl(e['start'])} naik ke {id_num(now, 2)} % (biasanya "
                             f"{id_num(ref, 2)} %). Produksi bilang setting proses normal.")

        if not items:
            items.append("Tidak ada isu besar dari data bulan ini, lanjutkan monitoring rutin.")
        urgent = st.get("RELEASE-URGENT", 0) + st.get("RECALL", 0)
        if urgent:
            items.append(f"Release urgent atas permintaan PPIC {urgent} mix bulan ini.")

        body = f"""# Notulen Rapat QC Bulanan {BULAN[m.month - 1]} {m.year}

| | |
|---|---|
| Tanggal rapat | {tgl(meet)} |
| Peserta | {QA_MGR} (QA Manager), {QC_SPV} (QC Supervisor), Hendra Gunawan, Lina Marlina (Verifikator), Yusuf Hidayat (QC Bahan Baku) |
| Periode data | produksi {m.strftime('%m/%Y')} |

## Ringkasan angka
Sampel sensory KimFis {ribu(len(k))} sampel, Pass {pct(pass_rate)}, TP1+ {pct(tp_dist.get('TP1+', 0))}, TP1- {pct(tp_dist.get('TP1-', 0))}, TP2 {pct(tp_dist.get('TP2+', 0) + tp_dist.get('TP2-', 0))}, TP3 {pct(tp_dist.get('TP3', 0))}. Kesesuaian grade KimFis dengan verifikator {pct(agree)} dari {ribu(len(v))} sampel yang diverifikasi.

Total {ribu(len(f))} mix diproduksi, {int(f['held'].sum())} mix sempat hold. Status akhir: release {int(st.get('RELEASE', 0) + st.get('RELEASE-URGENT', 0))}, blending {int(st.get('BLEND', 0))}, rework {int(st.get('REWORK', 0))}, reject {int(st.get('REJECT', 0))}, recall {int(st.get('RECALL', 0))}. Coffee test gagal {pct(ct_fail)}. Mikro TMS {int((mc['micro_status'] == 'Fail').sum())} dari {len(mc)} batch.

Bahan baku diterima {len(rc)} lot, conditional {int((rc['decision'] == 'Conditional').sum())}, reject {int((rc['decision'] == 'Reject').sum())}. Komplain masuk {len(cm)} ({cm_txt}). NCR baru {len(nc)}.

| Grade | Pass sensory | Viskositas rata-rata (cP) |
|---|---|---|
{grade_rows}

## Pembahasan
"""
        body += "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1)) + "\n"
        docs[f"meetings/Notulen_Rapat_QC_{m.strftime('%Y-%m')}.md"] = body
    return docs


# 6. RAG evaluation set (kept outside docs/ so it doesn't get indexed)

def eval_set(clean, truth):
    kim = clean["sensory_kimfis"].copy()
    kim["m"] = pd.to_datetime(kim["prod_date"]).dt.to_period("M")
    lab = clean["qc_lab_kimfis"].copy()
    lab["m"] = pd.to_datetime(lab["prod_date"]).dt.to_period("M")
    final = truth["final_status"].merge(clean["production_mix_log"][["mix_id", "prod_date", "line"]], on="mix_id")
    final["m"] = pd.to_datetime(final["prod_date"]).dt.to_period("M")
    rec = clean["rm_receiving"]
    mic = clean["micro_results"].copy()
    cmp = clean["complaints"]
    trn = clean["retail_transition_samples"]

    q = []

    def add(route, question, answer, source):
        q.append(dict(route=route, question=question, expected_answer=answer, source=source))

    # questions about standing documents
    add("rag", "Berapa batas maksimal PV minyak saat penerimaan, dan kapan masuk kategori Conditional?",
        "Maksimal 2,0 meq O2/kg. Conditional kalau PV 1,5 meq/kg atau lebih.", "SOP-QC-001 Rev 03")
    add("rag", "Berapa lama masa pakai kontrol sensory NDC-28P?", "30 hari, karena grade berbasis RBD Palm Oil.",
        "SOP-QC-005, SPEC-NDC-28P")
    add("rag", "Tahun 2025, berapa persen sampel yang diverifikasi acak oleh verifikator?", "25 % (SOP-QC-005 Rev 02).",
        "SOP-QC-005 Rev 02")
    add("rag", "Februari 2026, berapa persen sampel yang diverifikasi acak?", "30 % (SOP-QC-005 Rev 03 berlaku 05/01/2026).",
        "SOP-QC-005 Rev 03")
    add("rag", "Nilai -1 di lembar sensory Rev 03 sama dengan label apa di Rev 02?", "agak kurang", "SOP-QC-005 Rev 03")
    add("rag", "Berapa lama kontrol sensory boleh diperpanjang menurut SOP terbaru?",
        "Maksimal 14 hari setelah jatuh tempo dengan persetujuan QC Supervisor, setelah itu wajib kontrol sementara.",
        "SOP-QC-005 Rev 03")
    add("rag", "Bagaimana cara menyiapkan larutan untuk uji viskositas?",
        "20 g sampel dalam air demineral sampai 100 ml (20 % b/v), suhu 25 +/- 0,5 C, spindle LV-1 60 rpm, baca setelah 60 detik.",
        "SOP-QC-007")
    add("rag", "Apa yang harus dilakukan setelah lampu NIRS diganti?",
        "Cek bias dengan minimal 10 sampel referensi, koreksi model kalau bias kadar air lebih dari 0,1 %.", "SOP-QC-009 Rev 02")
    add("rag", "Berapa batas kadar air NDC-28P untuk produksi 15 November 2025?", "3,5 % (Spec Rev A).", "SPEC-NDC-28P Rev A")
    add("rag", "Berapa batas kadar air NDC-28P yang berlaku sekarang?", "3,2 % sejak 01/12/2025 (Spec Rev B).", "SPEC-NDC-28P Rev B")
    add("rag", "Bagaimana transisi grade di Line Retail dicek?",
        "Sampel tiap menit mulai sekitar menit ke-1 sampai 2 sampel berturut-turut pass, maksimal 12 sampel. Yang dicatat jam sampel.",
        "SOP-QC-015")
    add("rag", "Release normal menunggu hasil uji apa saja?",
        "Fisik-kimia dan sensory OK, plus mikro TPC, coliform, kapang khamir (H+3). Salmonella (H+5) boleh didahului.", "SOP-QC-012")
    rev = C.SOP_HOLD_REV05_DATE
    if rev <= C.END_DATE:
        after = min(C.END_DATE, rev + timedelta(days=20))
        before = rev - timedelta(days=70)
        add("rag", f"Apakah CRM-RT boleh release urgent pada {bln(after)}?",
            f"Tidak. SOP-QC-012 Rev 05 per {tgl(rev)} melarang release urgent untuk produk retail.", "SOP-QC-012 Rev 05")
        add("rag", f"Apakah CRM-RT boleh release urgent pada {bln(before)}?",
            "Boleh dengan permintaan tertulis PPIC, semua hasil fisik-kimia dan sensory OK, dan persetujuan QA Manager (Rev 04).",
            "SOP-QC-012 Rev 04")
    else:
        add("rag", "Apakah produk retail boleh release urgent?",
            "Boleh dengan permintaan tertulis PPIC, semua hasil fisik-kimia dan sensory OK, dan persetujuan QA Manager (SOP-QC-012 Rev 04).",
            "SOP-QC-012 Rev 04")

    # questions about what happened in this factory
    e = ev("spray_dryer_sensor_bias")
    if e["drawn"] and "dryer" in REF:
        burnt = NOTES.get("burnt_ncr")
        what = "TP3 gosong" if burnt else "warna produk lebih gelap"
        add("rag", f"Apa penyebab {what} di {lname(e['line'])} {kira(e['start'])} sampai {kira(e['end'])}?",
            f"Sensor suhu outlet TT-102 bias sekitar {id_num(e['magnitude'])} C lebih rendah, sehingga outlet aktual lebih panas."
            + (" Dugaan awal di NCR (nozzle) salah." if burnt else ""), f"{REF['dryer']}" + (", NCR terkait" if burnt else ""))
    e = ev("viscometer_drift")
    if e["drawn"] and "visc" in REF:
        add("rag", f"Berapa drift viskometer yang ditemukan {bln(e['end'])} dan kenapa tidak terdeteksi lebih awal?",
            f"Sekitar {round(100 * e['magnitude'])} % lebih tinggi. Cek harian dengan standar 5,0 cP tidak jalan karena standar habis.",
            REF["visc"])
    e = ev("bad_oil_lot")
    if e["drawn"] and "oil" in REF:
        add("rag", f"Lot minyak dari supplier mana yang masuk Conditional {kira(e['start'])}, dan grade apa yang perlu dipantau?",
            f"{C.MATERIALS[e['material']]['name']} dari {sup_name(e['supplier'])}, PV mendekati batas. Grade {e['grade']}.", REF["oil"])
    e = ev("silent_supplier_change")
    if e["drawn"] and "supplier" in REF:
        add("rag", f"Kapan supplier {C.MATERIALS[e['material']]['name'].lower()} berganti dan kenapa QC tidak tahu?",
            f"{tgl(e['start'])}, ke {sup_name(e['new_supplier']).rstrip('.')}. Memo RND {tgl(e['memo_date'])} hanya didistribusikan ke "
            "Purchasing, PPIC, Produksi.", f"{REF['supplier']}, notulen {bln(e['known'])}")
    if NOTES.get("coffee"):
        c = max(NOTES["coffee"], key=lambda x: x["rate"])
        add("rag", f"Apa penyebab coffee test gagal tinggi di {lname(c['line'])} bulan {BULAN[c['m'].month - 1]} {c['m'].year}?",
            "Terkait " + ", ditambah ".join(c["causes"]) + ".", "NCR coffee test dan memo terkait")
    e = ev("nirs_lamp_change")
    if e["drawn"] and "lamp_fix" in REF:
        add("rag", f"Berapa bias kadar air NIRS setelah lampu diganti {bln(e['start'])}?",
            f"+{id_num(e['bias'], 2)} %, dikoreksi {tgl(e['fix_date'])}.", REF["lamp_fix"])
    e = ev("homogenizer_wear")
    if e["drawn"] and "homog" in REF:
        add("rag", f"Apa yang ditemukan saat overhaul homogenizer {lname(e['line'])} {tgl(e['end'])}?",
            "Valve dan seat tahap pertama aus. Gauge tekanan masih dekat setpoint, tapi efisiensi homogenisasi turun.", REF["homog"])
    e = ev("cip_failure")
    if e["drawn"] and rev <= C.END_DATE:
        add("rag", "Kenapa SOP-QC-012 direvisi ke Rev 05?",
            f"Menindaklanjuti recall {bln(e['start'])} akibat CIP {lname(e['line'])} tidak tuntas.", f"SOP-QC-012 Rev 05, {REF.get('cip', '')}")
    e = ev("control_overdue")
    if e["drawn"] and "control" in REF:
        if e["start"] >= SENS_REV03:
            ans = f"Tidak. Kontrol dipakai sampai {tgl(e['end'])}, melebihi batas perpanjangan 14 hari di SOP-QC-005 Rev 03."
        else:
            ans = ("Sesuai SOP-QC-005 Rev 02 yang berlaku saat itu, karena perpanjangan boleh sampai kontrol baru siap. "
                   "Batas 14 hari baru berlaku di Rev 03.")
        add("rag+sql", f"Apakah perpanjangan kontrol {e['grade']} {bln(e['start'])} sesuai SOP?", ans,
            f"SOP-QC-005, {REF['control']}, sensory_controls")
    e = ev("silent_reformulation_costdown")
    if e["drawn"] and NOTES.get("costdown"):
        g = e["grade"]
        fm = lab[(lab["grade"] == g) & ~lab["is_retest"]]
        mb, ma = period(e["start"]) - 2, NOTES["costdown"][-1]
        p_b, p_a = (fm[fm["m"] == x]["protein_pct"].mean() for x in (mb, ma))
        add("sql", f"Berapa rata-rata protein {g} {BULAN[mb.month - 1]} {mb.year} dibanding {BULAN[ma.month - 1]} {ma.year}?",
            f"{id_num(p_b, 2)} % vs {id_num(p_a, 2)} %", "qc_lab_kimfis")
        add("rag", f"Kenapa protein {g} turun sejak {bln(e['start'])}?",
            "Dokumen hanya mencatat penurunannya di notulen dan bahwa RND belum menjawab. Penyebabnya tidak ada di dokumen, "
            "jawaban yang benar menyatakan itu, tidak menebak.", "notulen rapat QC")

    # questions answered from the tables
    k = kim[(kim["grade"] == "NDC-35") & (kim["m"] == pd.Period("2026-03"))]
    add("sql", "Berapa persen sampel KimFis NDC-35 yang Pass pada produksi Maret 2026?",
        pct((k["grade_result"] == "Pass").mean()), "sensory_kimfis")
    f5 = final[(final["line"] == "P1") & (final["m"] == pd.Period("2025-05"))]
    add("sql", "Berapa mix Plant 1 produksi Mei 2025 yang status akhirnya REJECT?", str(int((f5["final_status"] == "REJECT").sum())),
        "release_history / final status")
    v7 = lab[(lab["grade"] == "NDC-28P") & (lab["m"] == pd.Period("2025-07")) & ~lab["is_retest"]]["viscosity_cp"].mean()
    v9 = lab[(lab["grade"] == "NDC-28P") & (lab["m"] == pd.Period("2025-09")) & ~lab["is_retest"]]["viscosity_cp"].mean()
    add("sql", "Berapa rata-rata viskositas NDC-28P Juli 2025 dibanding September 2025?", f"{id_num(v7, 2)} cP vs {id_num(v9, 2)} cP",
        "qc_lab_kimfis")
    cond = rec[rec["decision"] == "Conditional"]["supplier_name"].value_counts()
    if len(cond):
        add("sql", "Supplier mana yang paling banyak lot Conditional?", f"{cond.index[0]} ({cond.iloc[0]} lot)", "rm_receiving")
    fc = cmp[(cmp["category"] == "Feathering di kopi") & (pd.to_datetime(cmp["received_date"]).dt.year == 2025)]
    add("sql", "Berapa komplain feathering yang masuk sepanjang 2025?", str(len(fc)), "complaints")
    ma = mic[(mic["line"] == "P2") & (pd.to_datetime(mic["prod_date"]).dt.to_period("M") == pd.Period("2026-04"))]
    add("sql", "Berapa batch Plant 2 produksi April 2026 yang hasil mikronya TMS?", str(int((ma["micro_status"] == "Fail").sum())),
        "micro_results")
    t = trn[(trn["from_grade"] == "MLK-RT") & (trn["to_grade"] == "CRM-RT")]
    first_pass = t[t["result"] == "Pass"].groupby("transition_id")["sample_seq"].min().mean()
    add("sql", "Rata-rata transisi MLK-RT ke CRM-RT baru pass di sampel ke berapa?", id_num(first_pass),
        "retail_transition_samples (sampel ke-n harus diturunkan dari urutan jam di data raw)")

    add("refuse", "Berapa harga jual NDC-35 per kg ke PT Kopi Instan Sejahtera?", "Tidak ada di dokumen, harus menolak menjawab.", "-")
    add("refuse", "Supplier HCO mana yang paling murah?", "Tidak ada informasi harga di dokumen.", "-")
    add("refuse", "Apa formula lengkap NDC-35?", "Formula tidak ada di dokumen QC.", "-")
    add("refuse", "Berapa gaji analis KimFis?", "Tidak ada di dokumen.", "-")
    return pd.DataFrame(q)


# 7. Entry point

def make_docs(clean, truth, rng):
    REF.clear()
    NOTES.clear()
    docs = {}
    docs.update(doc_sop.sop_docs())
    docs.update(doc_sop.spec_docs())
    docs.update(memos(clean, truth, rng))
    ncr_docs, ncr_list = ncrs(clean, truth, rng)
    docs.update(ncr_docs)
    docs.update(investigations(clean, rng))
    docs.update(logbooks(clean, rng))
    docs.update(meetings(clean, truth, ncr_list))
    truth["rag_eval_questions"] = eval_set(clean, truth)
    return docs
