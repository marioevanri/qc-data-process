"""Tested questions to the QC database, for the assistant to call.

Every function takes plain arguments (a batch number, a complaint number, a lot, a period),
runs fixed queries and returns a dict with:
    found   False when the batch, complaint or lot doesn't exist
    text    a short summary in Indonesian, this is what the model gets to read
    data    the same facts as tables, for the app to show

The model never writes SQL here. It only gets the text, and has to answer from it.
"""

import sqlite3
from difflib import get_close_matches
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "qc.db"
ACCEPTED_SENSORY = ("Pass", "TP1+", "TP1-")  # spec: Pass atau TP1 terhadap kontrol
# below these the lot comparison gets a warning. Rules of thumb, picked by hand, not from a test.
MIN_TP3 = 5
MIN_COMPARISON = 30


def read(sql, params=()):
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql(sql, con, params=params)


def number(x, digits=2):
    """3.2 -> '3,2' the way it's written in the sheets and specs."""
    if pd.isna(x):
        return "-"
    text = f"{x:.{digits}f}"
    # only trailing decimals go, 20 stays 20
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def percent(x):
    return f"{x:.1%}".replace(".", ",")


TEST_NAMES = {"ffa": "FFA", "pv": "PV", "moisture": "kadar air", "color_red": "warna merah", "de": "DE",
              "ph": "pH", "protein": "protein", "fat": "lemak", "solubility": "kelarutan", "tpc": "TPC"}


def not_found(kind, value, known):
    close = get_close_matches(value, known, n=3, cutoff=0.7)
    hint = f" Mungkin maksudnya: {', '.join(close)}." if close else ""
    return {"found": False, "text": f"{kind} {value} tidak ada di database.{hint}", "data": {}}


def spec_for(grade, prod_date):
    """Limits valid on the production date: per parameter the latest revision that had started."""
    spec = read("SELECT * FROM spec_limits WHERE grade = ? AND berlaku_mulai <= ?", (grade, prod_date))
    return spec.sort_values("berlaku_mulai").groupby("parameter").tail(1).reset_index(drop=True)


def out_of_spec(value, low, high, rule):
    if pd.isna(value):
        return False
    if rule == "Pass":
        return value != "Pass"
    return (pd.notna(low) and value < low) or (pd.notna(high) and value > high)


def limit_text(row):
    if row["syarat"]:
        return row["syarat"]
    low, high = row["batas_min"], row["batas_maks"]
    if pd.notna(low) and pd.notna(high):
        return f"{number(low)} sampai {number(high)}"
    return f"min {number(low)}" if pd.notna(low) else f"maks {number(high)}"


# status of one batch

def batch_status(batch_no, with_complaints=True):
    """with_complaints: False when called from trace_complaint, which lists them itself."""
    batch_no = batch_no.strip().upper()
    production = read("SELECT * FROM production_mix_log WHERE batch_no = ? ORDER BY mix_letter", (batch_no,))
    if production.empty:
        known = read("SELECT DISTINCT batch_no FROM production_mix_log")["batch_no"].tolist()
        return not_found("Batch", batch_no, known)
    grade, line, prod_date = production[["grade", "line", "prod_date"]].iloc[0]
    spec = spec_for(grade, prod_date)
    total = f"{int(production['mix_kg'].sum()):,}".replace(",", ".")
    lines = [f"Batch {batch_no}: {grade}, line {line}, produksi {prod_date}, {len(production)} mix "
             f"({', '.join(production['mix_letter'])}), total {total} kg."]
    revisions = spec[spec["parameter"] != "Umur simpan"].groupby("revisi")["parameter"].apply(list)
    lines.append("Spek yang dipakai: SPEC-" + grade + " " + ", ".join(
        f"Rev {rev}" + (f" untuk {', '.join(params)}" if len(revisions) > 1 and rev != "A" else "")
        for rev, params in revisions.items()) + f" (berlaku pada {prod_date}).")
    findings = []

    # raw material lots per mix, with what QC incoming decided about them
    lot_columns = ["oil_lot", "gss_lot", "protein_lot"]
    lots = production.melt(id_vars="mix_letter", value_vars=lot_columns, value_name="lot").dropna(subset=["lot"])
    receipts = read("SELECT internal_lot, material_name, decision, remarks FROM rm_receiving WHERE internal_lot IN ({})"
                    .format(",".join("?" * lots["lot"].nunique())), tuple(lots["lot"].unique()))
    used = lots.groupby("lot")["mix_letter"].apply(lambda m: ",".join(sorted(m))).reset_index().merge(
        receipts, left_on="lot", right_on="internal_lot", how="left")
    lines.append("Bahan baku: " + "; ".join(
        f"{r['lot']} {r['material_name'] if pd.notna(r['material_name']) else ''} (mix {r['mix_letter']}, "
        f"incoming {r['decision'] if pd.notna(r['decision']) else 'tidak tercatat'}"
        + (f": {r['remarks']}" if pd.notna(r["remarks"]) and r["remarks"] else "") + ")"
        for _, r in used.iterrows()) + ".")
    for _, r in used[used["decision"].isin(["Conditional", "Reject"])].iterrows():
        findings.append(f"Bahan baku {r['decision']}: {r['lot']} {r['material_name']} ({r['remarks']}), "
                        f"dipakai di mix {r['mix_letter']}")

    # physical-chemical: the latest result per sample, against the spec
    lab = read("SELECT * FROM qc_lab_final WHERE batch_no = ?", (batch_no,))
    retests = read("SELECT COUNT(*) AS n FROM qc_lab_kimfis WHERE batch_no = ? AND is_retest = 1", (batch_no,))["n"][0]
    lab_rows = []
    for _, s in spec[spec["tabel"] == "qc_lab_final"].iterrows():
        values = lab[s["kolom"]].dropna()
        if values.empty:
            continue
        bad = lab[lab[s["kolom"]].map(lambda v: out_of_spec(v, s["batas_min"], s["batas_maks"], s["syarat"]))]
        if s["syarat"]:
            summary = f"{(values == 'Pass').sum()} dari {len(values)} Pass"
        else:
            summary = f"{number(values.min())} sampai {number(values.max())}"
        lab_rows.append({"parameter": s["parameter"], "batas": limit_text(s), "hasil": summary,
                         "sampel": len(values), "di_luar_spek": len(bad)})
        for _, b in bad.iterrows():
            findings.append(f"{s['parameter']} {b['sample_uid']}: {number(b[s['kolom']]) if not s['syarat'] else b[s['kolom']]}"
                            f" (spek {limit_text(s)}, diuji {int(b['n_tests'])} kali)")
    lines.append(f"Kimia fisika (hasil terakhir per sampel, {len(lab)} sampel, {retests} retest):")
    lines += [f"- {r['parameter']}: {r['hasil']}, spek {r['batas']}"
              + (f", {r['di_luar_spek']} sampel di luar spek" if r["di_luar_spek"] else "") for r in lab_rows]

    # sensory, and what the verifikator said about the rejected samples
    sensory = read("SELECT * FROM sensory_kimfis WHERE batch_no = ?", (batch_no,))
    counts = sensory["grade_result"].value_counts()
    lines.append("Sensory KimFis: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + ".")
    rejected = sensory[~sensory["grade_result"].isin(ACCEPTED_SENSORY)]
    if not rejected.empty:
        verif = read(f"SELECT sample_uid, grade_result AS verifikator, notes AS catatan_verifikator "
                     f"FROM sensory_verifikator WHERE sample_uid IN ({','.join('?' * len(rejected))})",
                     tuple(rejected["sample_uid"]))
        rejected = rejected.merge(verif, on="sample_uid", how="left")
        for _, r in rejected.iterrows():
            what = f"{r['grade_result']}" + (f" {r['off_flavor_type']}" if pd.notna(r["off_flavor_type"]) else "")
            check = f", verifikator: {r['verifikator']}" if pd.notna(r["verifikator"]) else ", belum diverifikasi"
            findings.append(f"Sensory {r['sample_uid']}: {what} ({r['notes'] or '-'}){check}")

    # micro, one result per batch
    micro = read("SELECT * FROM micro_results WHERE batch_no = ?", (batch_no,))
    if micro.empty:
        lines.append("Mikro: belum ada hasil.")
    else:
        m = micro.iloc[0]
        tpc = number(m["tpc_cfu_g"], 0) if pd.notna(m["tpc_cfu_g"]) else "tidak terbaca di lembar"
        lines.append(f"Mikro: {m['micro_status']} (TPC {tpc}, coliform "
                     f"{'<10' if m['coliform_lt10'] else number(m['coliform_cfu_g'], 0)}, kapang khamir "
                     f"{'<10' if m['ym_lt10'] else number(m['ym_cfu_g'], 0)}, E. coli {m['ecoli']}, "
                     f"Salmonella {m['salmonella']}), hasil keluar {m['result_date']}.")
        if m["micro_status"] == "Fail":
            findings.append(f"Mikro TMS: {m['fail_reason']}")

    # release: the last status of every mix
    release = read("SELECT * FROM release_history WHERE batch_no = ? ORDER BY status_time", (batch_no,))
    last = release.groupby("mix_id").tail(1).sort_values("mix_id")
    lines.append("Status release terakhir per mix:")
    released_before_recall = {}
    for _, r in last.iterrows():
        line = f"- {r['mix_id']}: {r['status']} {r['status_time'][:16]}, alasan: {r['reason']}, diputuskan oleh {r['decided_by']}"
        # a recall only makes sense next to the release that let the mix go out
        before = release[(release["mix_id"] == r["mix_id"]) & (release["status_time"] < r["status_time"])
                         & (release["status"] != "QUARANTINE")]
        if r["status"] == "RECALL" and not before.empty:
            b = before.iloc[-1]
            line += f" (sebelumnya {b['status']} {b['status_time'][:16]}, alasan: {b['reason']})"
            released_before_recall[r["mix_id"]] = b["status"]
        lines.append(line)

    shipments = read("SELECT do_no, ship_date, customer_name, mixes, qty_kg FROM shipments WHERE batch_no = ?",
                     (batch_no,))
    if not shipments.empty:
        lines.append("Sudah dikirim: " + "; ".join(
            f"{r['do_no']} ke {r['customer_name']} {r['ship_date']} (mix {r['mixes']}, {r['qty_kg']} kg)"
            for _, r in shipments.iterrows()) + ".")
    complaints = pd.DataFrame()
    if with_complaints:
        complaints = read("SELECT complaint_id, received_date, customer_name, category, justified FROM complaints "
                          "WHERE batch_no = ? ORDER BY received_date", (batch_no,))
        if not complaints.empty:
            verdict = {1: "terbukti", 0: "tidak terbukti"}
            lines.append("Komplain untuk batch ini: " + "; ".join(
                f"{r['complaint_id']} {r['customer_name']} {r['received_date']} ({r['category']}, "
                f"{verdict.get(r['justified'], 'belum diputuskan')})" for _, r in complaints.iterrows()) + ".")
    lines.append("Temuan: " + ("; ".join(findings) if findings else "tidak ada hasil di luar spek.") )

    # the facts any answer about this batch needs, on the first line, so a short answer keeps them
    out_of_spec_parts = [f"{r['parameter']} {r['di_luar_spek']} sampel" for r in lab_rows if r["di_luar_spek"]]
    if not rejected.empty:
        confirmed = rejected["verifikator"].notna() & ~rejected["verifikator"].isin(ACCEPTED_SENSORY)
        out_of_spec_parts.append(f"sensory ditolak {len(rejected)} sampel ("
                                 + ", ".join(f"{k} {v}" for k, v in rejected["grade_result"].value_counts().items())
                                 + f"), {int(confirmed.sum())} dikonfirmasi verifikator")
    if not micro.empty and micro.iloc[0]["micro_status"] == "Fail":
        out_of_spec_parts.append(f"mikro ({micro.iloc[0]['fail_reason']})")
    statuses = []
    for status, part in last.groupby("status", sort=False):
        mixes_text = ",".join(m.split("-")[-1] + (f" sebelumnya {released_before_recall[m]}"
                                                   if m in released_before_recall else "") for m in part["mix_id"])
        statuses.append(f"{status} {len(part)} (mix {mixes_text})")
    flagged_lots = used[used["decision"].isin(["Conditional", "Reject"])]
    inti = [f"status terakhir {'; '.join(statuses) if statuses else 'belum ada'}",
            "di luar spek: " + ("; ".join(out_of_spec_parts) if out_of_spec_parts else "tidak ada")]
    if not flagged_lots.empty:
        inti.append("bahan baku " + "; ".join(f"{r['decision']} {r['lot']} ({r['remarks']})"
                                              for _, r in flagged_lots.iterrows()))
    inti.append("dikirim: " + ("; ".join(f"mix {r['mixes']} ke {r['customer_name']} ({r['do_no']})"
                                         for _, r in shipments.iterrows()) if not shipments.empty else "belum"))
    if not complaints.empty:
        inti.append("komplain: " + ", ".join(complaints["complaint_id"]))
    lines.insert(0, f"Inti batch {batch_no}: " + ". ".join(x[0].upper() + x[1:] for x in inti) + ".")
    return {"found": True, "text": "\n".join(lines),
            "data": {"produksi": production, "kimfis": pd.DataFrame(lab_rows), "sensory_ditolak": rejected,
                     "mikro": micro, "release": last, "pengiriman": shipments, "komplain": complaints,
                     "temuan": findings}}


# trace a complaint

def trace_complaint(complaint_id):
    complaint_id = complaint_id.strip().upper()
    complaint = read("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,))
    if complaint.empty:
        known = read("SELECT complaint_id FROM complaints")["complaint_id"].tolist()
        return not_found("Komplain", complaint_id, known)
    c = complaint.iloc[0]
    justified = {1: "terbukti", 0: "tidak terbukti"}.get(c["justified"], "belum diputuskan")
    lines = [f"Komplain {complaint_id} diterima {c['received_date']} dari {c['customer_name']}: "
             f"\"{c['description']}\" ({c['category']}, {c['grade']}, {c['qty_affected_kg']} kg terdampak). "
             f"Status {c['status']}, {justified}."]
    if not c["batch_no"]:
        lines.append(f"Batch belum tertelusur. Yang ditulis customer: {c['lot_text'] or 'tidak ada'}.")
        lines.insert(0, f"Inti komplain {complaint_id}: {c['category']}, {justified}. Batch belum tertelusur.")
        return {"found": True, "text": "\n".join(lines), "data": {"komplain": complaint}}
    lines.append(f"Tertelusur ke batch {c['batch_no']}, {c['do_no']} (sumber: {c['trace_source']}).")
    shipped = read("SELECT do_no, ship_date, customer_name, mixes, qty_kg FROM shipments WHERE batch_no = ?",
                   (c["batch_no"],))
    others = shipped[shipped["do_no"] != c["do_no"]]
    if not others.empty:
        lines.append("Batch yang sama juga dikirim ke: " + "; ".join(
            f"{r['customer_name']} ({r['do_no']}, {r['ship_date']})" for _, r in others.iterrows()) + ".")
    same_batch = read("SELECT complaint_id, customer_name, description FROM complaints "
                      "WHERE batch_no = ? AND complaint_id != ?", (c["batch_no"], complaint_id))
    if not same_batch.empty:
        lines.append("Komplain lain untuk batch ini: " + "; ".join(
            f"{r['complaint_id']} {r['customer_name']}" for _, r in same_batch.iterrows()) + ".")
    status = batch_status(c["batch_no"], with_complaints=False)
    sent = shipped[shipped["do_no"] == c["do_no"]]
    sent_text = f", isi kiriman mix {sent['mixes'].iloc[0]}" if not sent.empty else ""
    lines.insert(0, f"Inti komplain {complaint_id}: {c['category']}, {justified}. Tertelusur ke batch {c['batch_no']} "
                    f"lewat {c['do_no']} ke {c['customer_name']}{sent_text} (sumber: {c['trace_source']}).")
    lines.append("")
    lines.append(status["text"])
    return {"found": True, "text": "\n".join(lines), "data": {"komplain": complaint, **status["data"]}}


# where a raw material lot went

def lot_usage(lot):
    lot = lot.strip().upper()
    lot_columns = ["oil_lot", "gss_lot", "protein_lot"]
    receipt = read("SELECT * FROM rm_receiving WHERE internal_lot = ?", (lot,))
    mixes = read("SELECT * FROM production_mix_log WHERE oil_lot = ? OR gss_lot = ? OR protein_lot = ?",
                 (lot, lot, lot))
    if receipt.empty and mixes.empty:
        known = read("SELECT internal_lot FROM rm_receiving")["internal_lot"].tolist()
        return not_found("Lot", lot, known)
    lines = []
    if not receipt.empty:
        r = receipt.iloc[0]
        tested = [c[3:] for c in receipt.columns if c.startswith("qc_") and c != "qc_release_date" and pd.notna(r[c])]
        results = ", ".join(f"{TEST_NAMES.get(t, t)} COA {number(r['coa_' + t]) if pd.notna(r['coa_' + t]) else 'tidak dicatat'}"
                            f" / QC {number(r[f'qc_{t}'])}" for t in tested)
        lines.append(f"Lot {lot}: {r['material_name']} dari {r['supplier_name']} (lot supplier {r['supplier_lot']}), "
                     f"diterima {r['received_at'][:10]}, {r['qty_kg']} kg. Keputusan QC incoming: {r['decision']}"
                     + (f" ({r['remarks']})" if r["remarks"] else "") + f", oleh {r['inspector']}.")
        lines.append(f"Hasil uji: {results}.")
    else:
        lines.append(f"Lot {lot} dipakai di produksi tapi tidak ada di log penerimaan bahan baku.")
    incoming = "tidak ada di log penerimaan"
    if not receipt.empty:
        incoming = receipt["decision"].iloc[0] + (f" ({receipt['remarks'].iloc[0]})" if receipt["remarks"].iloc[0] else "")
    if mixes.empty:
        rejected = not receipt.empty and receipt["decision"].iloc[0] == "Reject"
        lines.append("Lot ini tidak dipakai di produksi, sesuai keputusan incoming Reject." if rejected
                     else "Lot ini belum dipakai di produksi.")
        lines.insert(0, f"Inti lot {lot}: incoming {incoming}. Tidak dipakai di produksi.")
        return {"found": True, "text": "\n".join(lines), "data": {"penerimaan": receipt}}

    used_in = mixes.groupby(["batch_no", "grade"])["mix_letter"].apply(lambda m: ",".join(sorted(m))).reset_index()
    lines.append(f"Dipakai di {len(mixes)} mix dari {len(used_in)} batch, produksi {mixes['prod_date'].min()} "
                 f"sampai {mixes['prod_date'].max()}: " + "; ".join(
                     f"{r['batch_no']} (mix {r['mix_letter']})" for _, r in used_in.iterrows()) + ".")

    # sensory of the samples from exactly those mixes, next to the same grade in the same weeks
    sensory = read("SELECT sample_uid, batch_no, sample_code, grade, prod_date, grade_result, off_flavor_type "
                   "FROM sensory_kimfis WHERE grade IN ({}) AND prod_date BETWEEN ? AND ?".format(
                       ",".join("?" * mixes["grade"].nunique())),
                   (*mixes["grade"].unique(), mixes["prod_date"].min(), mixes["prod_date"].max()))
    sensory["mix_id"] = sensory["batch_no"] + "-" + sensory["sample_code"].str[0]
    with_lot = sensory["mix_id"].isin(mixes["mix_id"])
    # the comparison group leaves out mixes that used another lot QC incoming didn't fully accept,
    # otherwise two Conditional lots in the same week hide each other
    flagged = set(read("SELECT internal_lot FROM rm_receiving WHERE decision != 'Accept'")["internal_lot"])
    period_mixes = read("SELECT mix_id, oil_lot, gss_lot, protein_lot FROM production_mix_log WHERE prod_date BETWEEN ? AND ?",
                        (mixes["prod_date"].min(), mixes["prod_date"].max()))
    other_flagged = set(period_mixes.loc[period_mixes[lot_columns].isin(flagged).any(axis=1), "mix_id"])
    clean = ~with_lot & ~sensory["mix_id"].isin(other_flagged)

    def tp3_text(part):
        """'TP3 52 dari 102 sampel (51,0%), jenis oxid 52': the count stays next to the percentage."""
        if part.empty:
            return "tidak ada sampel", 0
        tp3 = part[part["grade_result"] == "TP3"]
        kinds = tp3["off_flavor_type"].value_counts()
        kinds_text = (", jenis " + ", ".join(f"{k} {v}" for k, v in kinds.items())) if len(kinds) else ""
        return f"TP3 {len(tp3)} dari {len(part)} sampel ({percent(len(tp3) / len(part))}){kinds_text}", len(tp3)

    # The comparison group is cleaned of other flagged lots, the group with this lot isn't. When
    # some of its mixes also carry another flagged lot, their TP3 can't be put on this lot alone,
    # so the figure from mixes with only this lot leads. With the mixed figure first, the model
    # drew its conclusion from it even when the clean one was on the next line.
    other_lots = mixes[lot_columns].apply(
        lambda row: sorted(x for x in row.dropna() if x != lot and x in flagged), axis=1)
    shared = mixes.loc[other_lots.map(bool), "mix_id"]
    names = ", ".join(sorted({x for found in other_lots for x in found}))
    alone = with_lot & ~sensory["mix_id"].isin(shared)
    label = "mix dengan lot ini" if shared.empty else "mix yang hanya memakai lot ini"

    # both groups in one sentence: the rate with the lot means little without the rate without it
    alone_text, tp3_alone = tp3_text(sensory[alone])
    comparison_text, _ = tp3_text(sensory[clean])
    comparison = (f"{label} ({len(mixes) - len(shared)} mix) {alone_text}, dibanding pembanding (mix lain grade "
                  f"sama, periode sama, tanpa lot Conditional/Reject lain) {comparison_text}")
    if not shared.empty:
        with_text, _ = tp3_text(sensory[with_lot])
        comparison += f". {len(shared)} mix lain juga memakai {names}, kalau ikut dihitung: {with_text}"
    # rules of thumb, not a statistical test: samples from one mix aren't independent, so a
    # p-value over samples would look far more certain than it is
    caveats = []
    if not sensory[alone].empty and tp3_alone == 0:
        caveats.append(f"tidak ada TP3 di {label}")
    elif not sensory[alone].empty and tp3_alone < MIN_TP3:
        caveats.append(f"TP3 di {label} cuma {tp3_alone}, terlalu sedikit untuk menunjukkan pengaruh lot")
    if clean.sum() < MIN_COMPARISON:
        caveats.append(f"pembanding cuma {int(clean.sum())} sampel, perbandingannya lemah")
    if not shared.empty:
        caveats.append(f"{len(shared)} dari {len(mixes)} mix dengan lot ini juga memakai lot Conditional/Reject lain "
                       f"({names}), jadi TP3 di mix itu tidak bisa dibebankan ke lot ini saja")
    if caveats:
        lines.append("PERINGATAN: " + "; ".join(caveats) + ".")

    release = read("SELECT * FROM release_history WHERE mix_id IN ({}) ORDER BY status_time".format(
        ",".join("?" * len(mixes))), tuple(mixes["mix_id"]))
    final = release.groupby("mix_id").tail(1)["status"].value_counts()
    lines.append("Status terakhir mix-mix itu: " + ", ".join(f"{k} {v}" for k, v in final.items()) + ".")
    complaints = read("SELECT complaint_id, received_date, customer_name, category, batch_no FROM complaints "
                      "WHERE batch_no IN ({})".format(",".join("?" * len(used_in))), tuple(used_in["batch_no"]))
    if complaints.empty:
        lines.append("Tidak ada komplain untuk batch-batch itu.")
    else:
        lines.append("Komplain untuk batch-batch itu: " + "; ".join(
            f"{r['complaint_id']} {r['customer_name']} {r['received_date']} ({r['category']}, batch {r['batch_no']})"
            for _, r in complaints.iterrows()) + ".")
    lines.insert(0, f"Inti lot {lot}: incoming {incoming}. Dipakai di {len(mixes)} mix dari {len(used_in)} batch. "
                    f"Sensory {comparison}. Status terakhir mix: " + ", ".join(f"{k} {v}" for k, v in final.items())
                 + ". Komplain: " + (", ".join(complaints["complaint_id"]) if not complaints.empty else "tidak ada") + ".")
    return {"found": True, "text": "\n".join(lines),
            "data": {"penerimaan": receipt, "dipakai_di": used_in, "release": final, "komplain": complaints}}


# verifikator against KimFis

def verifikator_agreement(start=None, end=None, grade=None):
    """How often the verifikator's H+1 result agrees with KimFis on the same sample."""
    sql = ("SELECT v.sample_uid, v.grade, v.prod_date, v.verifikator_id, v.grade_result AS verifikator, "
           "k.grade_result AS kimfis, k.analyst_id FROM sensory_verifikator v "
           "JOIN sensory_kimfis k ON k.sample_uid = v.sample_uid WHERE 1 = 1")
    params = []
    if start:
        sql += " AND v.prod_date >= ?"
        params.append(str(start))
    if end:
        sql += " AND v.prod_date <= ?"
        params.append(str(end))
    if grade:
        sql += " AND v.grade = ?"
        params.append(grade)
    df = read(sql, tuple(params))
    if df.empty:
        return {"found": False, "text": "Tidak ada sampel verifikasi untuk periode atau grade itu.", "data": {}}
    # Pass / TP1 / TP2 / TP3, the direction of TP1 and TP2 left out
    df["kimfis_kelas"] = df["kimfis"].str[:3].replace({"Pas": "Pass"})
    df["verif_kelas"] = df["verifikator"].str[:3].replace({"Pas": "Pass"})
    df["sama_persis"] = df["kimfis"] == df["verifikator"]
    df["sama_kelas"] = df["kimfis_kelas"] == df["verif_kelas"]
    df["sama_keputusan"] = df["kimfis"].isin(ACCEPTED_SENSORY) == df["verifikator"].isin(ACCEPTED_SENSORY)

    def rate(part):
        return pd.Series({"sampel": len(part), "sama_persis": part["sama_persis"].mean(),
                          "sama_kelas": part["sama_kelas"].mean(), "sama_keputusan": part["sama_keputusan"].mean()})

    period = f"{start or df['prod_date'].min()} sampai {end or df['prod_date'].max()}"
    overall = rate(df)
    lines = [f"Verifikator vs KimFis, produksi {period}" + (f", grade {grade}" if grade else "")
             + f": {len(df)} sampel diverifikasi."]
    n = len(df)

    def share(column, same=True):
        """'27 dari 28 (96,4%)': with 28 samples one sample moves the rate by 3,6 points."""
        count = int(df[column].sum()) if same else int((~df[column]).sum())
        return f"{count} dari {n} ({percent(count / n)})"

    lines.append(f"Hasil persis sama {share('sama_persis')}, sama kelasnya (Pass/TP1/TP2/TP3) {share('sama_kelas')}, "
                 f"sama keputusannya (diterima Pass/TP1 atau ditolak) {share('sama_keputusan')}.")
    lines.append(f"Yang beda: hasil persis {share('sama_persis', False)}, kelas {share('sama_kelas', False)}, "
                 f"keputusan terima atau tolak {share('sama_keputusan', False)}.")
    by_verifikator = df.groupby("verifikator_id").apply(rate, include_groups=False)
    by_analyst = df.groupby("analyst_id").apply(rate, include_groups=False)
    by_grade = df.groupby("grade").apply(rate, include_groups=False)
    for title, table in (("Per verifikator", by_verifikator), ("Per analis KimFis", by_analyst),
                         ("Per grade", by_grade)):
        lines.append(f"{title} (sampel, sama kelas, sama keputusan): " + "; ".join(
            f"{i} {int(r['sampel'])}, {percent(r['sama_kelas'])}, {percent(r['sama_keputusan'])}" for i, r in table.iterrows()))
    confusion = pd.crosstab(df["kimfis_kelas"], df["verif_kelas"])
    lines.append("Tabel silang (baris KimFis, kolom verifikator): " + "; ".join(
        f"KimFis {i}: " + ", ".join(f"{c} {v}" for c, v in row.items() if v) for i, row in confusion.iterrows()))
    tp3_not_confirmed = int(((df["kimfis_kelas"] == "TP3") & (df["verif_kelas"] != "TP3")).sum())
    tp3_missed = int(((df["kimfis_kelas"] != "TP3") & (df["verif_kelas"] == "TP3")).sum())
    lines.append(f"TP3 dari KimFis yang tidak dikonfirmasi verifikator: {tp3_not_confirmed}. "
                 f"TP3 temuan verifikator yang lolos di KimFis: {tp3_missed}.")

    # which samples get verified matters for how to read the numbers above
    population = read("SELECT grade_result FROM sensory_kimfis WHERE 1 = 1"
                      + (" AND prod_date >= ?" if start else "") + (" AND prod_date <= ?" if end else "")
                      + (" AND grade = ?" if grade else ""), tuple(params))
    verified_share = df.groupby("kimfis_kelas").size() / population["grade_result"].str[:3].replace(
        {"Pas": "Pass"}).value_counts()
    shares = verified_share.dropna()
    lines.append("Porsi sampel KimFis yang ikut diverifikasi: " + ", ".join(
        f"{k} {percent(v)}" for k, v in shares.items()) + ".")
    not_random = len(shares) > 1 and shares.max() > 1.5 * shares.min()
    if not_random:
        lines.insert(1, f"PERINGATAN: sampel yang diverifikasi bukan acak. {shares.idxmax()} dari KimFis diverifikasi "
                        f"{percent(shares.max())}, {shares.idxmin()} hanya {percent(shares.min())}. Angka kesepakatan di "
                        f"bawah berlaku untuk sampel yang diverifikasi, bukan untuk semua produksi.")
    lines.insert(0, f"Inti verifikator vs KimFis: {n} sampel diverifikasi. Sama keputusan {share('sama_keputusan')}, "
                    f"sama kelas {share('sama_kelas')}."
                 + (" Sampel yang diverifikasi bukan acak." if not_random else ""))
    return {"found": True, "text": "\n".join(lines),
            "data": {"keseluruhan": overall, "per_verifikator": by_verifikator, "per_analis": by_analyst,
                     "per_grade": by_grade, "tabel_silang": confusion}}
