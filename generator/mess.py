# Turns the clean tables into the files you'd actually get from each department.
# Every department has its own habits: QC writes Indonesian headers and dd/mm/yyyy,
# production writes English headers and its own mix numbering, the micro lab writes MS/TMS,
# someone saves CSV from Excel with an Indonesian locale, and so on.
# Each raw row is mapped back to its clean record in truth/raw_row_map.csv.

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import config as C

MS = C.MESS

GRADE_VARIANTS = {
    "NDC-35": ["NDC 35", "ndc-35", "NDC35", "NDC-35 ", "Krimer 35"],
    "NDC-28P": ["NDC 28P", "ndc-28p", "NDC28P", "NDC-28 P", "NDC 28 Palm"],
    "FMP-26": ["FMP 26", "fmp-26", "FMP26", "FMP-26 ", "Filled Milk 26"],
    "CRM-RT": ["CRM RT", "crm-rt", "CRMRT", "Krimer Sachet", "CRM-RT "],
    "MLK-RT": ["MLK RT", "mlk-rt", "MLKRT", "Susu Retail", "MLK-RT "],
}

# people who type with a decimal comma most of the time
COMMA_PEOPLE = {"AN03", "AN06", "RM02"}
OPERATORS = ["Joko", "Slamet", "Budi", "Hari", "Wawan", "Eko"]


class RowMap:
    def __init__(self):
        self.rows = []

    def add(self, raw_file, raw_row, table, key, tags):
        self.rows.append(dict(raw_file=raw_file, raw_row=raw_row, table=table, clean_key=key,
                              mess=";".join(tags)))

    def frame(self):
        return pd.DataFrame(self.rows)


# 1. Small formatting helpers

def chance(rng, p):
    return rng.random() < p


def num(x, rng, comma=False, nd=None, tags=None):
    # format a measured number the way a person types it
    if x is None or (isinstance(x, float) and np.isnan(x)):
        if tags is not None and nd:
            tags.append("text_in_numeric")
        return nd or ""
    if isinstance(x, (bool, np.bool_)):
        return str(x)
    s = f"{x:g}" if not isinstance(x, (int, np.integer)) else str(x)
    if comma and "." in s:
        s = s.replace(".", ",")
        if tags is not None:
            tags.append("decimal_comma")
    return s


def grade_txt(g, rng, tags):
    if chance(rng, MS["grade_variant"]):
        tags.append("grade_variant")
        return str(rng.choice(GRADE_VARIANTS[g]))
    return g


def person_txt(code, rng, tags):
    pool = {**C.KIMFIS_ANALYSTS, **C.VERIFIKATORS}
    full = pool[code]["name"]
    first, last = full.split()[0], full.split()[1]
    if chance(rng, MS["analyst_variant"]):
        tags.append("analyst_variant")
        return str(rng.choice([first.lower(), first.upper(), code, f"{first} {last[0]}.", full]))
    return first


def batch_txt(b, rng, tags, p=None):
    if not chance(rng, MS["batch_typo"] if p is None else p):
        return b
    tags.append("batch_typo")
    op = rng.choice(["swap", "lower", "space", "dash", "O0", "trail"])
    if op == "swap":
        i = int(rng.integers(0, 7))
        return b[:i] + b[i + 1] + b[i] + b[i + 2:]
    if op == "lower":
        return b[:-2] + b[-2:].lower()
    if op == "space":
        return b[:6] + " " + b[6:]
    if op == "dash":
        return f"{b[:6]}-{b[6:8]}-{b[8:]}"
    if op == "O0":
        return b.replace("0", "O", 1)
    return b + " "


def sample_code_txt(code, rng, tags, style_p=0.02):
    if chance(rng, style_p):
        tags.append("sample_code_variant")
        return str(rng.choice([f"{code[0]}-{code[1:]}", code.lower(), f"{code[1:]}{code[0]}", f"{code[0]} {code[1:]}"]))
    return code


def dmy(d):
    return f"{d:%d/%m/%Y}"


def hm(ts, rng, tags):
    if chance(rng, 0.10):
        tags.append("time_with_dot")
        return f"{ts:%H.%M}"
    return f"{ts:%H:%M}"


def excel_serial(d):
    return (pd.Timestamp(d) - pd.Timestamp("1899-12-30")).days


def add_duplicates(rows, tag_rows, rng, near_cols=(), p_exact=None, p_near=None):
    # append exact and near duplicates right after the original row
    p_exact = MS["exact_duplicate"] if p_exact is None else p_exact
    p_near = MS["near_duplicate"] if p_near is None else p_near
    out_rows, out_tags = [], []
    for r, t in zip(rows, tag_rows):
        out_rows.append(r); out_tags.append(t)
        if chance(rng, p_exact):
            out_rows.append(dict(r)); out_tags.append((t[0], t[1] + ["exact_duplicate"]))
        elif near_cols and chance(rng, p_near):
            nr = dict(r)
            col = str(rng.choice(list(near_cols)))
            v = str(nr.get(col, ""))
            try:
                f = float(v.replace(",", "."))
                nr[col] = f"{f + rng.choice([-1, 1]) * max(0.01, abs(f) * 0.02):.2f}"
            except ValueError:
                pass
            out_rows.append(nr); out_tags.append((t[0], t[1] + [f"near_duplicate:{col}"]))
    return out_rows, out_tags


def to_frame(rows, cols):
    return pd.DataFrame(rows, columns=cols)


def flush(files, rmap, rel, table, rows, tags, cols):
    files[rel] = to_frame(rows, cols)
    for i, (key, tg) in enumerate(tags):
        rmap.add(rel, i, table, key, tg)


# 2. Raw material receiving log (QC bahan baku, one sheet per year)

DECISION_TXT = {"Accept": ["Accept", "OK", "Diterima", "accept", "Terima"],
                "Conditional": ["Conditional", "Diterima bersyarat", "OK bersyarat", "Cond."],
                "Reject": ["Reject", "Tolak", "Ditolak", "REJECT"]}

RM_PARAMS = [("ffa", "FFA (%)"), ("pv", "PV (meq/kg)"), ("moisture", "Kadar Air (%)"), ("color_red", "Warna (R)"),
             ("de", "DE"), ("ph", "pH"), ("protein", "Protein (%)"), ("fat", "Lemak (%)"),
             ("solubility", "Kelarutan (ml)"), ("tpc", "TPC (cfu/g)")]


def raw_receiving(rec, files, rmap, rng):
    cols = ["No", "Tgl Terima", "Jam", "Kode Bahan", "Nama Bahan", "Supplier", "No Lot Supplier", "Lot Internal",
            "Qty", "Satuan"]
    for _, lab in RM_PARAMS:
        cols += [f"COA {lab}", f"QC {lab}"]
    cols += ["Keputusan", "Keterangan", "Inspektor", "Tgl Release"]
    rec = rec.copy()
    rec["year"] = pd.to_datetime(rec["received_at"]).dt.year
    for year, g in rec.groupby("year"):
        rows, tags = [], []
        for i, r in enumerate(g.itertuples(index=False), start=1):
            t = []
            insp = "RM01" if r.inspector == "Yusuf Hidayat" else "RM02"
            comma = insp in COMMA_PEOPLE and chance(rng, 0.7)
            d = pd.Timestamp(r.received_at)
            if chance(rng, MS["excel_serial_date"]):
                dtxt = str(excel_serial(d)); t.append("excel_serial_date")
            elif insp == "RM02" or chance(rng, MS["date_format_mix"]):
                dtxt = f"{d.day}-{d:%b-%y}"; t.append("date_format_mix")
            else:
                dtxt = dmy(d)
            sup = r.supplier_name
            if chance(rng, MS["supplier_alias"]):
                sup = str(rng.choice(C.SUPPLIER_ALIASES[r.supplier_id])); t.append("supplier_alias")
            qty, unit = str(r.qty_kg), "kg"
            if chance(rng, 0.15):
                qty, unit = num(round(r.qty_kg / 1000, 2), rng, comma=True), "ton"; t.append("unit_ton")
            row = {"No": i, "Tgl Terima": dtxt, "Jam": f"{d:%H:%M}",
                   "Kode Bahan": "" if chance(rng, 0.04) else r.material_code, "Nama Bahan": r.material_name,
                   "Supplier": sup, "No Lot Supplier": r.supplier_lot, "Lot Internal": r.internal_lot,
                   "Qty": qty, "Satuan": unit}
            coa_missing = chance(rng, 0.05)
            if coa_missing:
                t.append("coa_missing")
            for p, lab in RM_PARAMS:
                cv, qv = getattr(r, f"coa_{p}", np.nan), getattr(r, f"qc_{p}", np.nan)
                row[f"COA {lab}"] = ("lihat COA" if coa_missing and not pd.isna(cv) and chance(rng, 0.3) else "") if coa_missing \
                    else num(None if pd.isna(cv) else round(float(cv), 3 if p in ("ffa", "moisture") else 2), rng, comma)
                if p == "de" and pd.isna(qv) and not pd.isna(cv):
                    row[f"QC {lab}"] = "-"
                else:
                    row[f"QC {lab}"] = num(None if pd.isna(qv) else round(float(qv), 3 if p in ("ffa", "moisture") else 2), rng, comma)
            row["Keputusan"] = str(rng.choice(DECISION_TXT[r.decision]));
            if row["Keputusan"] != r.decision:
                t.append("decision_variant")
            row["Keterangan"] = r.remarks
            row["Inspektor"] = r.inspector.split()[0]
            row["Tgl Release"] = dmy(r.qc_release_date) if not pd.isna(r.qc_release_date) else ""
            rows.append(row); tags.append((r.receipt_id, t))
        rows, tags = add_duplicates(rows, tags, rng)
        flush(files, rmap, f"rm_receiving/Log_Penerimaan_RM_{year}.csv", "rm_receiving", rows, tags, cols)


# 3. Production mix log (production department, English headers, own mix numbering)

def raw_production(mix_log, files, rmap, rng, trial_mixes=()):
    cols = ["Date", "Line", "Product", "Batch", "Mix No", "Start", "Finish", "Qty (kg)", "Oil Lot", "GSS Lot",
            "Protein Lot", "Inlet (C)", "Outlet (C)", "Homog P1 (bar)", "Homog P2 (bar)", "Feed TS (%)",
            "Emul Temp (C)", "Operator", "Remarks"]
    from simulate import get_event, is_active
    ev_dry, ev_hom = get_event("spray_dryer_sensor_bias"), get_event("homogenizer_wear")
    ev_cip, pt = get_event("cip_failure"), get_event("production_trial")
    rows, tags = [], []
    for r in mix_log.sort_values("start").itertuples(index=False):
        t = []
        b = r.batch_no
        prod_batch = f"{b[:6]}/{b[6:8]}/{b[8:]}"
        remarks = ""
        d = r.prod_date
        if r.after_grade_change:
            remarks = "ganti grade"
        if r.line == ev_dry["line"] and is_active(ev_dry, d) and chance(rng, 0.08):
            remarks = str(rng.choice(["outlet susah naik, inlet dinaikkan", "outlet naik turun", "inlet dinaikkan sedikit"]))
        if r.line == ev_hom["line"] and is_active(ev_hom, d) and chance(rng, 0.05):
            remarks = str(rng.choice(["homog agak bunyi", "tekanan homog turun dikit, disetel ulang", "cek homog"]))
        if r.line == ev_cip["line"] and d == ev_cip["start"] and r.seq_in_day == 1:
            remarks = "CIP ulang, valve CIP error"
        # production knows about its own trials and sometimes writes it down, QC doesn't read this column
        if r.line == pt["line"] and is_active(pt, d) and chance(rng, 0.35):
            remarks = str(rng.choice(["trial inlet turun (hemat gas)", "trial setting inlet", "trial"]))
        if r.mix_id in trial_mixes and chance(rng, 0.6):
            remarks = str(rng.choice(["trial RND", "trial formula RND", "mix trial, info RND"]))

        def lot(x):
            if chance(rng, 0.015):
                t.append("lot_typo")
                return str(rng.choice([x.replace("-", "", 1), x[:-2] + x[-1], x.lower(), x + " "]))
            return x

        def val(x, nd=1):
            if chance(rng, 0.03):
                t.append("missing_cell"); return ""
            if chance(rng, MS["decimal_shift"]):
                t.append("decimal_shift"); return f"{x * 10:.{nd}f}"
            return f"{x:.{nd}f}"

        row = {"Date": f"{d:%d-%m-%Y}", "Line": r.line if not chance(rng, 0.05) else r.line.lower(),
               "Product": grade_txt(r.grade, rng, t), "Batch": prod_batch, "Mix No": r.seq_in_day,
               "Start": f"{r.start:%H:%M}", "Finish": f"{r.end:%H:%M}", "Qty (kg)": r.mix_kg,
               "Oil Lot": lot(r.oil_lot), "GSS Lot": lot(r.gss_lot), "Protein Lot": lot(r.protein_lot),
               "Inlet (C)": val(r.inlet_temp), "Outlet (C)": val(r.outlet_temp), "Homog P1 (bar)": val(r.homog_p1_bar, 0),
               "Homog P2 (bar)": val(r.homog_p2_bar, 0), "Feed TS (%)": f"{round(r.feed_solids * 2) / 2:.1f}",
               "Emul Temp (C)": val(r.emulsion_temp), "Operator": str(rng.choice(OPERATORS)), "Remarks": remarks}
        if r.end.date() > r.start.date():
            t.append("finish_after_midnight")
        rows.append(row); tags.append((r.mix_id, t))
    rows, tags = add_duplicates(rows, tags, rng, p_near=0)
    flush(files, rmap, "production/Production_Mix_Log.csv", "production_mix_log", rows, tags, cols)


def raw_logger(logger, files, rng):
    # machine data: ISO timestamps, but outages, frozen sensors, sentinel values, restart duplicates
    lg = logger.copy()
    lg["timestamp"] = pd.to_datetime(lg["timestamp"])
    days = lg["timestamp"].dt.normalize().unique()
    for _ in range(MS["logger_gap_days"]):
        d0 = pd.Timestamp(rng.choice(days))
        line = rng.choice(["P1", "P2", "RT"])
        hrs = int(rng.integers(6, 40))
        lg = lg[~((lg["line"] == line) & (lg["timestamp"] >= d0) & (lg["timestamp"] < d0 + pd.Timedelta(hours=hrs)))]
    lg = lg.reset_index(drop=True)
    sensors = ["inlet_temp", "outlet_temp", "homog_p1_bar", "homog_p2_bar", "emulsion_temp", "ambient_rh"]
    for _ in range(MS["stuck_sensor_events"]):
        i = int(rng.integers(0, len(lg) - 50))
        col = rng.choice(sensors)
        n = int(rng.integers(8, 40))
        same_line = lg.index[(lg.index >= i) & (lg["line"] == lg.loc[i, "line"])][:n]
        lg.loc[same_line, col] = lg.loc[i, col]
    for col in sensors:
        m = rng.random(len(lg)) < MS["sentinel_value"]
        lg.loc[m, col] = rng.choice([0, 9999], size=m.sum())
    # logger restart writes the last few readings again
    dup_idx = []
    for _ in range(12):
        i = int(rng.integers(10, len(lg)))
        dup_idx += list(range(i - 6, i))
    lg = pd.concat([lg, lg.loc[dup_idx]]).sort_values(["line", "timestamp"], kind="stable").reset_index(drop=True)
    lg = lg.rename(columns={"timestamp": "Timestamp", "inlet_temp": "TT101_Inlet", "outlet_temp": "TT102_Outlet",
                            "homog_p1_bar": "PT201_Homog1", "homog_p2_bar": "PT202_Homog2",
                            "emulsion_temp": "TT301_Emul", "ambient_rh": "RH_Ambient"})
    lg["month"] = lg["Timestamp"].dt.strftime("%Y-%m")
    for (line, month), g in lg.groupby(["line", "month"]):
        out = g.drop(columns=["line", "month"]).copy()
        out["Timestamp"] = out["Timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
        files[f"production/logger/Dryer_{line}_{month}.csv"] = out


# 4. KimFis chem-phys lab, monthly sheets, schema changes in January 2026

LAB_V1 = ["Tgl Produksi", "No Batch", "Grade", "Kode Sampel", "Jam Sampling", "Jam Uji", "Analis", "KA (%)",
          "Lemak (%)", "Protein (%)", "Visko (cP)", "Brix", "BD (g/ml)", "Kelarutan (ml)", "Wettability (s)",
          "L*", "pH", "Coffee Test", "Ket"]
LAB_V2 = ["Tgl Produksi", "Line", "No Batch", "Grade", "Kode Sampel", "Jam Sampling", "Jam Uji", "KA (%)",
          "Lemak (%)", "Protein (%)", "Viskositas (cP)", "Brix", "Bulk Density", "Kelarutan (ml)",
          "Wettability (s)", "L*", "pH", "Coffee Test", "Retest (Y/N)", "Analis", "Ket"]
SCHEMA_V2_FROM = date(2026, 1, 1)


def raw_lab(lab, files, rmap, rng):
    lab = lab.sort_values("test_time").reset_index(drop=True)
    # occasional swap of two samples' results inside the same batch (wrong cup, wrong label)
    swap_pairs = []
    by_batch = lab.groupby("batch_no").groups
    for b, idx in by_batch.items():
        if len(idx) >= 2 and chance(rng, MS["wrong_sample_swap"] * 3):
            a, c = rng.choice(list(idx), size=2, replace=False)
            swap_pairs.append((a, c))
    vals = ["moisture_pct", "viscosity_cp", "brix"]
    swapped = set()
    for a, c in swap_pairs:
        lab.loc[[a, c], vals] = lab.loc[[c, a], vals].to_numpy()
        swapped |= {a, c}

    months = {}
    for i, r in lab.iterrows():
        t = ["wrong_sample_swap"] if i in swapped else []
        tt = pd.Timestamp(r["test_time"])
        month = tt.strftime("%Y-%m")
        if chance(rng, MS["late_entry"] * 0.2) and tt.day >= 27:
            month = (tt + pd.Timedelta(days=7)).strftime("%Y-%m"); t.append("late_entry_next_month_file")
        v2 = tt.date() >= SCHEMA_V2_FROM
        comma = r["analyst_id"] in COMMA_PEOPLE and chance(rng, 0.7)
        st = pd.Timestamp(r["sample_time"])
        prod = r["prod_date"]
        if st.hour < 7 and chance(rng, 0.3):
            prod = st.date(); t.append("night_shift_date_is_sample_date")

        def m(x, nd, col):
            if pd.isna(x):
                return ""
            if chance(rng, MS["missing_cell"]):
                t.append(f"missing_cell:{col}"); return ""
            if chance(rng, MS["text_in_numeric"]):
                t.append(f"text_in_numeric:{col}"); return str(rng.choice(["ND", "-", "tdk diuji", "retest", "?"]))
            if chance(rng, MS["decimal_shift"]):
                t.append(f"decimal_shift:{col}"); x = x * 10
            return num(round(float(x), nd), rng, comma, tags=t)

        bd = r.get("bulk_density")
        if not pd.isna(bd) and r["analyst_id"] == "AN04" and chance(rng, 0.3):
            bd_txt = str(int(round(bd * 1000))); t.append("bulk_in_g_per_L")
        else:
            bd_txt = m(bd, 3, "bulk")
        row = {
            "Tgl Produksi": dmy(prod), "Line": r["line"], "No Batch": batch_txt(r["batch_no"], rng, t),
            "Grade": grade_txt(r["grade"], rng, t), "Kode Sampel": sample_code_txt(r["sample_code"], rng, t),
            "Jam Sampling": hm(st, rng, t), "Jam Uji": hm(tt, rng, t), "Analis": person_txt(r["analyst_id"], rng, t),
            "KA (%)": m(r["moisture_pct"], 2, "moisture"), "Lemak (%)": m(r.get("fat_pct"), 2, "fat"),
            "Protein (%)": m(r.get("protein_pct"), 2, "protein"), "Brix": m(r["brix"], 1, "brix"),
            "Kelarutan (ml)": m(r.get("solubility_ml"), 2, "solubility"),
            "Wettability (s)": m(r.get("wettability_s"), 0, "wettability"), "L*": m(r.get("L_star"), 1, "L"),
            "pH": m(r.get("ph"), 2, "ph"), "Coffee Test": r.get("coffee_test") if isinstance(r.get("coffee_test"), str) else "",
        }
        visc = m(r["viscosity_cp"], 2, "viscosity")
        ket = ""
        if r["is_retest"]:
            if v2:
                row["Retest (Y/N)"] = "Y"
            elif chance(rng, 0.6):
                ket = "retest"
            else:
                t.append("retest_unmarked")
        elif v2:
            row["Retest (Y/N)"] = "N" if chance(rng, 0.8) else ""
        if row["Coffee Test"] and chance(rng, 0.3):
            row["Coffee Test"] = {"Pass": rng.choice(["OK", "pass", "Tidak feathering"]),
                                  "Fail": rng.choice(["feathering", "fail", "NG"])}[row["Coffee Test"]]
            t.append("coffee_text_variant")
        if v2:
            row["Viskositas (cP)"], row["Bulk Density"] = visc, bd_txt
        else:
            row["Visko (cP)"], row["BD (g/ml)"] = visc, bd_txt
        row["Ket"] = ket
        months.setdefault(month, ([], []))
        months[month][0].append(row); months[month][1].append((f"{r['sample_uid']}@{tt:%Y-%m-%d %H:%M}", t))

    euro_months = set(rng.choice(sorted(months), size=3, replace=False))
    for month, (rows, tags) in sorted(months.items()):
        rows, tags = add_duplicates(rows, tags, rng, near_cols=("KA (%)", "Brix"))
        cols = LAB_V2 if date.fromisoformat(month + "-01") >= SCHEMA_V2_FROM else LAB_V1
        rel = f"qc_lab/KimFis_{month}.csv"
        flush(files, rmap, rel, "qc_lab_kimfis", rows, tags, cols)
        if month in euro_months:
            files[rel] = ("EXCEL_ID", files[rel])  # written later with ; and decimal comma


# 5. NIRS instrument export (one file per year, plus spectra)

def raw_nirs(nres, nspec, files, rmap, rng):
    model = {"NDC-35": "NDC35_v3", "NDC-28P": "NDC28P_v2", "FMP-26": "FMP26_v1", "CRM-RT": "CRMRT_v2",
             "MLK-RT": "MLKRT_v1"}
    spec = nspec.set_index("scan_id")
    nres = nres.sort_values("scan_time").reset_index(drop=True)
    years = {}
    for r in nres.itertuples(index=False):
        t = []
        if r.is_control:
            name = str(rng.choice([f"CTRL {r.grade}", f"kontrol {C.PRODUCTS[r.grade]['code']}",
                                   f"{r.control_id}", f"Kontrol {r.grade} {r.prod_date:%d%m}"]))
        else:
            uid = r.sample_uid
            b, code = uid[:-3], uid[-2:]
            name = str(rng.choice([f"{b} {code}", f"{code}-{b}", f"{b}{code}", f"{code} {b[-4:]}"],
                                  p=[0.55, 0.2, 0.15, 0.1]))
            if name.startswith(code + " ") and len(name) < 12:
                t.append("short_sample_name")
        status = "OK"
        if r.pred_moisture < 0 or r.pred_fat < 0:
            status = "Outlier"
        row = {"Scan No": r.scan_id, "Date Time": f"{pd.Timestamp(r.scan_time):%Y-%m-%d %H:%M:%S}",
               "Sample Name": name, "Product Model": model[r.grade], "Moisture": r.pred_moisture,
               "Fat": r.pred_fat, "Protein": r.pred_protein, "Status": status, "Instrument": r.instrument}
        y = pd.Timestamp(r.scan_time).year
        years.setdefault(y, ([], [], []))
        years[y][0].append(row); years[y][1].append((r.scan_id, t)); years[y][2].append(r.scan_id)
        # analyst rescans the same cup now and then
        if chance(rng, 0.03):
            rs = dict(row)
            rs["Scan No"] = r.scan_id + "R"
            rs["Date Time"] = f"{pd.Timestamp(r.scan_time) + pd.Timedelta(minutes=2):%Y-%m-%d %H:%M:%S}"
            for k in ("Moisture", "Fat", "Protein"):
                rs[k] = round(rs[k] + rng.normal(0, 0.08), 2)
            years[y][0].append(rs); years[y][1].append((r.scan_id, t + ["rescan"])); years[y][2].append(r.scan_id + "R")
        # random junk scans: trials, competitor samples, test scans
        if chance(rng, 0.004):
            junk = dict(row)
            junk["Scan No"] = r.scan_id + "X"
            junk["Sample Name"] = str(rng.choice(["test", "trial RND", "sampel kompetitor", "cek alat", "xx"]))
            years[y][0].append(junk); years[y][1].append(("", ["junk_scan"])); years[y][2].append(r.scan_id + "X")
    cols = ["Scan No", "Date Time", "Sample Name", "Product Model", "Moisture", "Fat", "Protein", "Status", "Instrument"]
    for y, (rows, tags, ids) in years.items():
        flush(files, rmap, f"nirs/NIRS_Export_{y}.csv", "nirs_results", rows, tags, cols)
        base_ids = [i.rstrip("RX") for i in ids]
        sp = spec.loc[base_ids].reset_index(drop=True)
        noise = np.where(np.array([i.endswith(("R", "X")) for i in ids])[:, None],
                         rng.normal(0, 0.0015, sp.shape), 0.0)
        sp = (sp + noise).round(5)
        sp.insert(0, "Scan No", ids)
        files[f"nirs/NIRS_Spectra_{y}.csv.gz"] = sp


# 6. Sensory sheets

LABEL_V1 = {-2: ["kurang", "krg", "2-"], -1: ["agak kurang", "agk kurang", "AK", "1-", "kurang dikit"],
            0: ["pass", "0", "OK", "sesuai"], 1: ["agak lebih", "agk lebih", "AL", "1+"], 2: ["lebih", "2+", "lbh"]}
LABEL_V2 = {-2: ["-2"], -1: ["-1", "1-"], 0: ["0"], 1: ["1", "+1", "1+"], 2: ["2", "+2"]}
GRADE_TXT = {"Pass": ["Pass", "pass", "PASS", "P"], "TP1-": ["TP1-", "TP 1-", "TP1 -", "TP1(-)"],
             "TP1+": ["TP1+", "TP 1+", "TP1 +", "TP1(+)"], "TP2-": ["TP2-", "TP 2-"], "TP2+": ["TP2+", "TP 2+"],
             "TP3": ["TP3", "TP 3", "tp3"]}
SENS_V2_FROM = date(2026, 1, 5)


def typo(text, rng):
    if not text or not chance(rng, 0.12):
        return text
    i = int(rng.integers(0, max(1, len(text) - 1)))
    return text[:i] + text[i + 1:] if chance(rng, 0.5) else text[:i] + text[i] * 2 + text[i + 1:]


def pick(d, k, rng, p_first=0.75):
    opts = d[k]
    if len(opts) == 1 or chance(rng, p_first):
        return opts[0], False
    return str(rng.choice(opts[1:])), True


def raw_sensory(kim, ver, controls, trn, files, rmap, rng):
    kim = kim.sort_values("test_time").reset_index(drop=True)
    months = {}
    for r in kim.itertuples(index=False):
        t = []
        tt = pd.Timestamp(r.test_time)
        v2 = tt.date() >= SENS_V2_FROM
        lab = LABEL_V2 if v2 else LABEL_V1
        row = {"Tgl": dmy(r.prod_date), "Batch": batch_txt(r.batch_no, rng, t), "Grade": grade_txt(r.grade, rng, t),
               "Sampel": sample_code_txt(r.sample_code, rng, t), "Jam": hm(tt, rng, t),
               "Analis": person_txt(r.analyst_id, rng, t), "Kontrol": r.control_id if v2 else ""}
        for col, a in (("Creamy", "creamy"), ("Mouthfeel", "mouthfeel"), ("Milky", "milky"), ("Manis", "sweetness")):
            v, var = pick(lab, getattr(r, f"score_{a}"), rng)
            if chance(rng, MS["missing_cell"] * 0.5):
                v = ""; t.append(f"missing_cell:{col}")
            elif var:
                t.append("label_variant")
            row[col] = v
        g, var = pick(GRADE_TXT, r.grade_result, rng, 0.8)
        if var:
            t.append("grade_label_variant")
        row["Grade Sensory" if v2 else "Hasil"] = g
        row["Catatan"] = typo(r.notes or "", rng)
        months.setdefault(tt.strftime("%Y-%m"), ([], []))
        months[tt.strftime("%Y-%m")][0].append(row); months[tt.strftime("%Y-%m")][1].append((r.sample_uid, t))
    for month, (rows, tags) in sorted(months.items()):
        v2 = date.fromisoformat(month + "-01") >= date(2026, 1, 1)
        cols = (["Tgl", "Batch", "Grade", "Sampel", "Jam", "Analis", "Kontrol", "Creamy", "Mouthfeel", "Milky",
                 "Manis", "Grade Sensory"] + (["Hasil"] if month == "2026-01" else []) + ["Catatan"] if v2 else
                ["Tgl", "Batch", "Grade", "Sampel", "Jam", "Analis", "Creamy", "Mouthfeel", "Milky", "Manis",
                 "Hasil", "Catatan"])
        rows, tags = add_duplicates(rows, tags, rng)
        flush(files, rmap, f"sensory/Sensory_KimFis_{month}.csv", "sensory_kimfis", rows, tags, cols)

    # verifikator keeps one running file and writes sample codes as A-2
    rows, tags = [], []
    for r in ver.sort_values("test_time").itertuples(index=False):
        t = []
        row = {"Tgl Uji": dmy(r.test_time), "Batch": batch_txt(r.batch_no, rng, t, p=0.04),
               "Sampel": f"{r.sample_code[0]}-{r.sample_code[1:]}", "Grade": grade_txt(r.grade, rng, t),
               "Verifikator": person_txt(r.verifikator_id, rng, t)}
        for col, a in (("Creamy", "creamy"), ("Mouthfeel", "mouthfeel"), ("Milky", "milky"), ("Manis", "sweetness")):
            row[col] = pick(LABEL_V2, getattr(r, f"score_{a}"), rng, 0.9)[0]
        row["Hasil Verif"] = pick(GRADE_TXT, r.grade_result, rng, 0.9)[0]
        row["Hasil KimFis"] = pick(GRADE_TXT, r.kimfis_grade, rng, 0.9)[0] if chance(rng, 0.85) else ""
        if row["Hasil KimFis"] == "":
            t.append("missing_cell:Hasil KimFis")
        row["Catatan"] = typo(r.notes or "", rng)
        rows.append(row); tags.append((r.sample_uid, t))
    rows, tags = add_duplicates(rows, tags, rng)
    cols = ["Tgl Uji", "Batch", "Sampel", "Grade", "Verifikator", "Creamy", "Mouthfeel", "Milky", "Manis",
            "Hasil Verif", "Hasil KimFis", "Catatan"]
    flush(files, rmap, "sensory/Verifikasi_H1.csv", "sensory_verifikator", rows, tags, cols)

    # control log, end date blank while a control is still in use
    rows, tags = [], []
    for r in controls.itertuples(index=False):
        t = []
        end = "" if r.end_use > C.END_DATE else dmy(r.end_use)
        rows.append({"ID Kontrol": r.control_id, "Grade": grade_txt(r.grade, rng, t), "Batch Asal": r.source_batch,
                     "Tgl Mulai": dmy(r.start_use), "Tgl Expired": dmy(r.due_date), "Tgl Ganti": end,
                     "Keterangan": r.note})
        tags.append((r.control_id, t))
    flush(files, rmap, "sensory/Log_Kontrol_Sensory.csv", "sensory_controls", rows, tags,
          ["ID Kontrol", "Grade", "Batch Asal", "Tgl Mulai", "Tgl Expired", "Tgl Ganti", "Keterangan"])

    # retail transitions: no transition id, no sequence, just sample times
    rows, tags = [], []
    for r in trn.sort_values("sample_time").itertuples(index=False):
        t = []
        res = r.result if not chance(rng, 0.25) else {"Pass": "OK", "Belum Pass": str(rng.choice(["NG", "blm pass", "campur"]))}[r.result]
        rows.append({"Tanggal": dmy(r.sample_time), "Dari": grade_txt(r.from_grade, rng, t),
                     "Ke": grade_txt(r.to_grade, rng, t), "Jam Sampel": f"{pd.Timestamp(r.sample_time):%H:%M:%S}",
                     "Hasil": res, "Analis": person_txt(r.analyst_id, rng, t), "Ket": r.handling})
        tags.append((f"{r.transition_id}#{r.sample_seq}", t))
    flush(files, rmap, "sensory/Transisi_Retail.csv", "retail_transition_samples", rows, tags,
          ["Tanggal", "Dari", "Ke", "Jam Sampel", "Hasil", "Analis", "Ket"])


# 7. Micro lab, release status, warehouse, complaints

def tpc_txt(v, rng, t):
    if v < 10:
        return "<10"
    style = rng.choice(["plain", "sci_x", "sci_e"], p=[0.6, 0.3, 0.1])
    if style == "plain":
        return str(v)
    t.append("tpc_scientific")
    e = int(np.floor(np.log10(v)))
    m = v / 10 ** e
    if style == "sci_x":
        return f"{m:.1f}".replace(".", ",") + f" x 10^{e}"
    return f"{m:.1E}".replace("E+0", "E+")


def raw_micro(mic, files, rmap, rng):
    years = {}
    for r in mic.itertuples(index=False):
        t = []
        row = {"Tgl Terima": dmy(r.received_lab), "No Batch": batch_txt(r.batch_no, rng, t),
               "Grade": grade_txt(r.grade, rng, t), "TPC (cfu/g)": tpc_txt(r.tpc_cfu_g, rng, t),
               "Coliform": "<10" if r.coliform_lt10 else str(r.coliform_cfu_g),
               "Kapang Khamir": "<10" if r.ym_lt10 else str(r.ym_cfu_g), "E. coli": r.ecoli,
               "Salmonella": r.salmonella, "Tgl Hasil": dmy(r.result_date),
               "Status": "MS" if r.micro_status == "Pass" else "TMS"}
        years.setdefault(r.prod_date.year, ([], []))
        years[r.prod_date.year][0].append(row); years[r.prod_date.year][1].append((r.batch_no, t))
    cols = ["Tgl Terima", "No Batch", "Grade", "TPC (cfu/g)", "Coliform", "Kapang Khamir", "E. coli", "Salmonella",
            "Tgl Hasil", "Status"]
    for y, (rows, tags) in years.items():
        rows, tags = add_duplicates(rows, tags, rng, p_near=0)
        flush(files, rmap, f"micro/Hasil_Mikro_{y}.csv", "micro_results", rows, tags, cols)


STATUS_TXT = {"QUARANTINE": ["QUARANTINE", "Karantina", "QRT"], "HOLD": ["HOLD", "Hold", "Tahan"],
              "RELEASE": ["RELEASE", "Release", "Rilis", "RLS"], "REJECT": ["REJECT", "Reject", "Tolak"],
              "BLEND": ["BLEND", "Blending"], "REWORK": ["REWORK", "Rework", "Proses ulang"],
              "RELEASE-URGENT": ["RELEASE-URGENT", "Release (urgent)", "Rilis darurat"], "RECALL": ["RECALL", "Recall"]}


def raw_release(hist, files, rmap, rng):
    rows, tags = [], []
    h = hist.sort_values("status_time")
    # routine releases of a whole batch at the same moment often get typed as one row
    grouped = h.groupby(["batch_no", "status_time", "status"])
    for (b, ts, st), g in grouped:
        letters = [m.rsplit("-", 1)[1] for m in g["mix_id"]]
        if len(g) > 1 and st in ("RELEASE", "QUARANTINE") and chance(rng, 0.4):
            t = ["batch_level_row"]
            mix_txt = "ALL" if chance(rng, 0.5) else f"{letters[0]}-{letters[-1]}"
            r0 = g.iloc[0]
            rows.append({"Waktu": f"{ts:%d/%m/%Y %H:%M}", "No Batch": batch_txt(b, rng, t), "Mix": mix_txt,
                         "Grade": grade_txt(r0["grade"], rng, t), "Status": pick(STATUS_TXT, st, rng, 0.7)[0],
                         "Alasan": r0["reason"], "Oleh": r0["decided_by"]})
            tags.append((";".join(g["mix_id"]) + f"@{st}", t))
            continue
        for _, r in g.iterrows():
            t = []
            stxt, var = pick(STATUS_TXT, st, rng, 0.7)
            if var:
                t.append("status_variant")
            rows.append({"Waktu": f"{ts:%d/%m/%Y %H:%M}", "No Batch": batch_txt(b, rng, t),
                         "Mix": r["mix_id"].rsplit("-", 1)[1], "Grade": grade_txt(r["grade"], rng, t), "Status": stxt,
                         "Alasan": r["reason"], "Oleh": r["decided_by"]})
            tags.append((f"{r['mix_id']}@{st}", t))
    flush(files, rmap, "release/Status_Release.csv", "release_history", rows, tags,
          ["Waktu", "No Batch", "Mix", "Grade", "Status", "Alasan", "Oleh"])


CUSTOMER_TXT = {"C01": ["PT Kopi Instan Sejahtera", "Kopi Instan Sejahtera", "PT. KIS", "KIS"],
                "C02": ["PT Minuman Segar Abadi", "Minuman Segar Abadi", "PT MSA", "MSA"],
                "C03": ["PT Roti Mentari Pagi", "Roti Mentari", "PT. Roti Mentari Pagi"],
                "C04": ["CV Kedai Kopi Rakyat", "Kedai Kopi Rakyat", "CV KKR"],
                "C05": ["PT Distribusi Retail Jatim", "DRJ", "PT. Distribusi Retail Jatim"],
                "C06": ["PT Mitra Swalayan Nusantara", "Mitra Swalayan", "PT MSN"]}


def raw_shipments(ship, files, rmap, rng):
    years = {}
    for r in ship.itertuples(index=False):
        t = []
        cust = pick(CUSTOMER_TXT, r.customer_id, rng, 0.6)[0]
        bags = r.qty_kg // 25 if C.PRODUCTS[r.grade]["segment"] == "B2B" else r.qty_kg // 10
        row = {"No DO": r.do_no, "Tgl Kirim": dmy(r.ship_date), "Customer": cust,
               "No Batch": batch_txt(r.batch_no, rng, t, p=0.02), "Mix": r.mixes, "Produk": grade_txt(r.grade, rng, t),
               "Qty (kg)": r.qty_kg, "Jumlah Kemasan": bags}
        years.setdefault(r.ship_date.year, ([], []))
        years[r.ship_date.year][0].append(row); years[r.ship_date.year][1].append((r.do_no, t))
    for y, (rows, tags) in years.items():
        flush(files, rmap, f"warehouse/Pengiriman_{y}.csv", "shipments", rows, tags,
              ["No DO", "Tgl Kirim", "Customer", "No Batch", "Mix", "Produk", "Qty (kg)", "Jumlah Kemasan"])


def raw_complaints(cmp, files, rmap, rng):
    rows, tags = [], []
    for r in cmp.itertuples(index=False):
        t = []
        u = rng.random()
        if u < 0.15:
            ref = ""; t.append("lot_ref_missing")
        elif u < 0.25:
            ref = f"kiriman tgl {pd.Timestamp(r.received_date) - pd.Timedelta(days=int(rng.integers(5, 30))):%d/%m}"
            t.append("lot_ref_vague")
        elif u < 0.35:
            ref = batch_txt(r.batch_no, rng, [], p=1.0); t.append("lot_ref_typo")
        elif u < 0.45:
            ref = r.batch_no[:8]; t.append("lot_ref_partial")
        else:
            ref = str(rng.choice([r.batch_no, f"LOT {r.batch_no}", f"Lot: {r.batch_no}"]))
        hasil = ""
        if r.status == "Closed":
            hasil = "Terbukti" if r.justified else "Tidak terbukti"
        rows.append({"No Komplain": r.complaint_id, "Tgl Terima": dmy(r.received_date),
                     "Customer": pick(CUSTOMER_TXT, r.customer_id, rng, 0.6)[0], "Produk": grade_txt(r.grade, rng, t),
                     "No Lot (dari customer)": ref, "Keluhan": r.description, "Qty Terdampak (kg)": r.qty_affected_kg,
                     "Status": r.status, "Hasil Investigasi": hasil})
        tags.append((r.complaint_id, t))
    flush(files, rmap, "complaints/Komplain_Customer.csv", "complaints", rows, tags,
          ["No Komplain", "Tgl Terima", "Customer", "Produk", "No Lot (dari customer)", "Keluhan",
           "Qty Terdampak (kg)", "Status", "Hasil Investigasi"])


# 8. Entry point

def excel_id(df):
    # what Excel with Indonesian regional settings does to a CSV: ; separator, decimal comma
    out = df.copy()
    for c in out.columns:
        if c.startswith(("Jam", "Tgl")):
            continue
        out[c] = out[c].map(lambda v: v.replace(".", ",") if isinstance(v, str) and v.replace(".", "", 1).isdigit() else v)
    return out.to_csv(sep=";", index=False)


def make_raw(clean, nspec, rng, trial_mixes=()):
    files, rmap = {}, RowMap()
    mix_log = clean["production_mix_log"].copy()
    mix_log["start"] = pd.to_datetime(mix_log["start"])
    mix_log["end"] = pd.to_datetime(mix_log["end"])
    mix_log = mix_log.sort_values("start")
    mix_log["seq_in_day"] = mix_log.groupby(["prod_date", "line"]).cumcount() + 1
    prev = mix_log.groupby(["prod_date", "line"])["grade"].shift()
    mix_log["after_grade_change"] = prev.notna() & (prev != mix_log["grade"])
    raw_receiving(clean["rm_receiving"], files, rmap, rng)
    raw_production(mix_log, files, rmap, rng, set(trial_mixes))
    raw_logger(clean["dryer_logger"], files, rng)
    raw_lab(clean["qc_lab_kimfis"], files, rmap, rng)
    raw_nirs(clean["nirs_results"], nspec, files, rmap, rng)
    raw_sensory(clean["sensory_kimfis"], clean["sensory_verifikator"], clean["sensory_controls"],
                clean["retail_transition_samples"], files, rmap, rng)
    raw_micro(clean["micro_results"], files, rmap, rng)
    raw_release(clean["release_history"], files, rmap, rng)
    raw_shipments(clean["shipments"], files, rmap, rng)
    raw_complaints(clean["complaints"], files, rmap, rng)
    for k, v in list(files.items()):
        if isinstance(v, tuple) and v[0] == "EXCEL_ID":
            files[k] = excel_id(v[1])
    return files, rmap.frame()
