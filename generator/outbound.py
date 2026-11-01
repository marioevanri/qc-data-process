# Everything after the sample leaves the lab: retests, retail grade transitions, micro,
# hold/release decisions, shipments and customer complaints.

from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd

import config as C
from quality import kimfis_on_shift
from simulate import get_event, is_active, is_wet, spec_on

QC_SPV = "Agus Salim"
QA_MGR = "Ratna Kusuma"


# 1. Lab retests: out-of-spec results usually get re-measured

def lab_spec_fails(row, d):
    s = C.PRODUCTS[row["grade"]]["spec"]
    fails = []
    if row["moisture_pct"] > spec_on(row["grade"], "moisture_max", d):
        fails.append("moisture")
    lo, hi = s["visc"]
    if not lo <= row["viscosity_cp"] <= hi:
        fails.append("viscosity")
    if not pd.isna(row.get("fat_pct")) and not s["fat"][0] <= row["fat_pct"] <= s["fat"][1]:
        fails.append("fat")
    if not pd.isna(row.get("bulk_density")) and not s["bulk"][0] <= row["bulk_density"] <= s["bulk"][1]:
        fails.append("bulk")
    if not pd.isna(row.get("solubility_ml")) and row["solubility_ml"] > s["solub_max"]:
        fails.append("solubility")
    if not pd.isna(row.get("L_star")) and row["L_star"] < s["L_min"]:
        fails.append("color")
    if row.get("coffee_test") == "Fail":
        fails.append("coffee_test")
    return fails


def add_retests(lab, samples, rng):
    truth = samples.set_index("sample_uid")
    lab = lab.copy()
    lab["is_retest"] = False
    lab["retest_of"] = None
    extra = []
    for _, r in lab.iterrows():
        fails = lab_spec_fails(r, r["prod_date"])
        fails = [f for f in fails if f in ("moisture", "viscosity", "fat")]
        if not fails or rng.random() > 0.7:
            continue
        t = truth.loc[r["sample_uid"]]
        new = r.copy()
        new["test_time"] = r["test_time"] + timedelta(minutes=int(rng.integers(40, 150)))
        new["is_retest"] = True
        new["retest_of"] = ",".join(fails)
        new["moisture_pct"] = round(t["moisture"] + rng.normal(0, 0.06), 2)
        vf = r["viscosity_cp"] / max(t["visc"], 0.1)  # same instrument, same drift
        new["viscosity_cp"] = round(t["visc"] * vf + rng.normal(0, 0.06), 2)
        if "fat" in fails:
            new["fat_pct"] = round(t["fat"] + rng.normal(0, 0.15), 2)
        extra.append(new)
    out = pd.concat([lab, pd.DataFrame(extra)], ignore_index=True)
    return out.sort_values(["test_time", "sample_uid"]).reset_index(drop=True)


def final_lab(lab):
    # the value that counts for release is the latest test of each sample
    return lab.sort_values("test_time").groupby("sample_uid", as_index=False).last()


# 2. Retail line grade transitions (sampled minute by minute until it passes)

def retail_transitions(mixes, rng):
    rt = mixes[(mixes["line"] == "RT") & (mixes["after_grade_change"])]
    rows, truth = [], []
    for k, r in enumerate(rt.itertuples(index=False), start=1):
        tid = f"TRN-{k:04d}"
        t0 = pd.Timestamp(r.start)
        tau = rng.lognormal(np.log(1.0), 0.35) * (1.2 if r.prev_grade == "MLK-RT" else 1.0)
        c0 = rng.uniform(0.6, 0.9)
        analyst = kimfis_on_shift(t0)
        thr = 0.08 * C.KIMFIS_ANALYSTS[analyst]["deadband"] / 0.5
        passes, m = 0, 0
        truth.append(dict(transition_id=tid, true_start=t0, tau_min=tau, c0=c0))
        while m < 12:
            m += 1
            ts = t0 + timedelta(minutes=m, seconds=int(rng.integers(0, 40)))
            c = max(0.0, c0 * np.exp(-m / tau) + rng.normal(0, 0.01))
            ok = c + rng.normal(0, 0.025) < thr
            rows.append(dict(
                transition_id=tid, prod_date=r.prod_date, line="RT", from_grade=r.prev_grade, to_grade=r.grade,
                batch_no=r.batch_no, mix_letter=r.mix_letter, sample_seq=m, sample_time=ts.round("s"),
                analyst_id=analyst, result="Pass" if ok else "Belum Pass",
                handling="" if ok else "disisihkan, dicampur bertahap ke produk pass",
                true_contamination=c,
            ))
            passes = passes + 1 if ok else 0
            if passes >= 2:
                break
    return pd.DataFrame(rows), pd.DataFrame(truth)


# 3. Micro per batch (daily composite)

def micro(mixes, rng):
    ev = get_event("cip_failure")
    b = mixes.groupby("batch_no", as_index=False).agg(prod_date=("prod_date", "first"), line=("line", "first"),
                                                     grade=("grade", "first"))
    rows = []
    for r in b.itertuples(index=False):
        p = C.PRODUCTS[r.grade]
        median = 250 if p["protein_src"] == "RM-CAS" else 900
        tpc = median * rng.lognormal(0, 0.7)
        coli = 0 if rng.random() > 0.005 else int(rng.integers(10, 30))
        if r.line == ev["line"] and is_active(ev, r.prod_date):
            tpc *= rng.uniform(15, 60)
            coli = int(rng.integers(10, 80)) if rng.random() < 0.6 else coli
        ym = rng.lognormal(np.log(4), 0.8)
        res_day = r.prod_date + timedelta(days=3)
        if res_day.weekday() == 6:
            res_day += timedelta(days=1)
        tpc = int(round(tpc, -1))
        why = []
        if tpc > p["spec"]["tpc_max"]: why.append(f"TPC {tpc}")
        if ym > p["spec"]["ym_max"]: why.append(f"kapang/khamir {int(round(ym))}")
        if coli > 10: why.append(f"coliform {int(coli)}")
        fail = bool(why)
        rows.append(dict(
            batch_no=r.batch_no, prod_date=r.prod_date, line=r.line, grade=r.grade,
            received_lab=r.prod_date + timedelta(days=1), result_date=res_day,
            salmonella_result_date=r.prod_date + timedelta(days=5),
            tpc_cfu_g=tpc, coliform_cfu_g=int(coli), coliform_lt10=coli < 10,
            ym_cfu_g=int(round(ym)), ym_lt10=ym < 10, ecoli="Negatif", salmonella="Negatif/25g",
            micro_status="Fail" if fail else "Pass", fail_reason=", ".join(why),
        ))
    return pd.DataFrame(rows)


# 4. Hold and release decisions per mix (history of status changes)

def urgent_rate(grade, d):
    seg = C.PRODUCTS[grade]["segment"]
    if seg == "Retail":
        return 0.0 if d >= C.SOP_HOLD_REV05_DATE else 0.05
    return 0.08


def release_decisions(mixes, lab_final, kimfis, verif, micro_df, rng):
    lab_by_mix = lab_final.assign(mix_id=lab_final["sample_uid"].str[:-1]).groupby("mix_id")
    kim_by_mix = kimfis.assign(mix_id=kimfis["sample_uid"].str[:-1]).groupby("mix_id")
    ver = verif.assign(mix_id=verif["sample_uid"].str[:-1])
    ver_by_mix = {k: g for k, g in ver.groupby("mix_id")}
    mic = micro_df.set_index("batch_no")
    hist, final = [], []

    def add(mix, ts, status, reason, by):
        hist.append(dict(mix_id=mix.mix_id, batch_no=mix.batch_no, grade=mix.grade, line=mix.line,
                         status_time=pd.Timestamp(ts).round("min"), status=status, reason=reason, decided_by=by))

    for mx in mixes.itertuples(index=False):
        labm = lab_by_mix.get_group(mx.mix_id)
        kim = kim_by_mix.get_group(mx.mix_id)
        vm = ver_by_mix.get(mx.mix_id)
        mi = mic.loc[mx.batch_no]
        micro_ok = mi["micro_status"] == "Pass"
        micro_time = datetime.combine(mi["result_date"], time(10)) + timedelta(minutes=int(rng.integers(0, 120)))

        add(mx, pd.Timestamp(mx.end) + timedelta(hours=1), "QUARANTINE", "menunggu hasil QC", "sistem")
        t_k = kim["test_time"].max() + timedelta(hours=1)
        spec_fails = sorted({f for _, r in labm.iterrows() for f in lab_spec_fails(r, mx.prod_date)})
        sens_bad = kim[kim["grade_result"].isin(["TP2+", "TP2-", "TP3"])]
        status, rel_time = None, None

        if not spec_fails and sens_bad.empty:
            # from SOP-QC-012 Rev 05 an urgent release needs a clean 48 h TPC pre-read first
            pre_read_ok = micro_ok or mx.prod_date < C.SOP_HOLD_REV05_DATE
            if pre_read_ok and rng.random() < urgent_rate(mx.grade, mx.prod_date):
                add(mx, t_k, "RELEASE-URGENT", "kiriman mendesak, rilis sebelum hasil mikro", QA_MGR)
                status, rel_time = "RELEASE-URGENT", t_k
                if not micro_ok:
                    add(mx, micro_time, "RECALL", f"hasil mikro gagal ({mi['fail_reason']})", QA_MGR)
                    status = "RECALL"
            elif micro_ok:
                add(mx, micro_time, "RELEASE", "semua parameter OK", QC_SPV)
                status, rel_time = "RELEASE", micro_time
            else:
                add(mx, micro_time, "HOLD", f"hasil mikro gagal ({mi['fail_reason']})", QC_SPV)
                add(mx, micro_time + timedelta(days=1), "REJECT", "mikro di luar spesifikasi", QA_MGR)
                status = "REJECT"
        else:
            reasons = spec_fails + [f"sensory {g}" for g in sorted(set(sens_bad["grade_result"]))]
            add(mx, t_k, "HOLD", ", ".join(reasons), QC_SPV)
            t_v = (vm["test_time"].max() if vm is not None else t_k + timedelta(days=1)) + timedelta(hours=2)
            off_types = set(kim["off_flavor_type"].dropna())
            ver_grades = set(vm["grade_result"]) if vm is not None else set()
            ver_bad = ver_grades & {"TP2+", "TP2-", "TP3"}
            if not micro_ok:
                add(mx, max(t_v, micro_time), "REJECT", "mikro di luar spesifikasi", QA_MGR)
                status = "REJECT"
            elif off_types & {"oxid", "burnt"} and (vm is None or "TP3" in ver_grades):
                add(mx, t_v, "REJECT", "off-flavor dikonfirmasi verifikator", QA_MGR)
                status = "REJECT"
            elif "moisture" in spec_fails:
                add(mx, t_v, "REWORK", "kadar air di atas spek, dikeringkan ulang / blending", QC_SPV)
                status = "REWORK"
            elif ver_bad or "coffee_test" in spec_fails or "mixgrade" in off_types:
                add(mx, t_v, "BLEND", "blending 1:4 dengan mix pass", QC_SPV)
                status = "BLEND"
            else:
                why = "verifikator tidak konfirmasi temuan" if not sens_bad.empty else "retest/deviasi disetujui"
                ts = max(t_v, micro_time)
                add(mx, ts, "RELEASE", why, QA_MGR if spec_fails else QC_SPV)
                status, rel_time = "RELEASE", ts
        final.append(dict(mix_id=mx.mix_id, final_status=status, release_time=rel_time))
    return pd.DataFrame(hist), pd.DataFrame(final)


# 5. Shipments

def shipments(mixes, final, rng):
    m = mixes.merge(final, on="mix_id")
    m = m[m["final_status"].isin(["RELEASE", "RELEASE-URGENT", "RECALL"])].copy()
    cust_by_grade = {}
    for cid, c in C.CUSTOMERS.items():
        for g in c["grades"]:
            cust_by_grade.setdefault(g, []).append(cid)
    rows = []
    n = 0
    for batch, g in m.groupby("batch_no"):
        grade = g["grade"].iloc[0]
        custs = cust_by_grade[grade]
        # most batches go to one customer, some get split
        if len(g) < 3 or rng.random() > 0.2:
            groups = [g]
        else:
            cut = len(g) // 2
            groups = [g.iloc[:cut], g.iloc[cut:]]
        for part in groups:
            urgent = (part["final_status"] != "RELEASE").any()
            base = pd.Timestamp(part["release_time"].max())
            ship = (base + timedelta(days=int(rng.integers(0, 2) if urgent else rng.integers(1, 14)))).date()
            n += 1
            cid = str(rng.choice(custs))
            rows.append(dict(
                do_no=f"DO-{ship:%y%m}-{n:05d}", ship_date=ship, customer_id=cid,
                customer_name=C.CUSTOMERS[cid]["name"], batch_no=batch, grade=grade,
                mixes=",".join(part["mix_letter"]), qty_kg=int(part["mix_kg"].sum() * 0.97 // 25 * 25),
            ))
    return pd.DataFrame(rows).sort_values("ship_date").reset_index(drop=True)


# 6. Customer complaints, triggered by what was actually wrong with the product

COMPLAINT_TEXT = {
    "Off-flavor tengik": ["Customer lapor produk bau tengik waktu karung dibuka",
                          "Rasa oily/tengik muncul setelah dicampur kopi, beberapa karung",
                          "Aroma tidak segar, cenderung tengik, minta investigasi lot"],
    "Feathering di kopi": ["Krimer pecah/menggumpal saat dicampur kopi panas",
                           "Ada gumpalan putih mengapung di permukaan kopi",
                           "Feathering di aplikasi kopi tubruk, customer minta penggantian"],
    "Caking / menggumpal": ["Produk menggumpal keras di dalam kemasan", "Banyak gumpalan, susah dituang dari sachet",
                            "Serbuk lembab dan menggumpal saat diterima gudang customer"],
    "Bintik hitam": ["Ditemukan bintik hitam/coklat di produk", "Ada partikel gosong saat dilarutkan"],
    "Kurang creamy": ["Rasa kurang creamy dibanding kiriman sebelumnya", "Mouthfeel lebih encer, body kurang",
                      "Customer bilang krimer 'kurang nendang' dibanding biasanya"],
    "Mikro": ["Hasil uji mikro lab customer, TPC melebihi spesifikasi"],
    "Kemasan / lain-lain": ["Kemasan bocor di beberapa karton", "Ditemukan serpihan plastik di satu karung",
                            "Label lot tidak terbaca", "Jumlah karung tidak sesuai surat jalan"],
}


def complaints(ship, mixes, mq, samples, rng):
    q = mixes[["mix_id", "batch_no", "mix_letter", "grade", "prod_date"]].merge(mq, on="mix_id")
    q = q.set_index(["batch_no", "mix_letter"])
    rows = []
    n = 0
    end = pd.Timestamp(C.END_DATE)
    for s in ship.itertuples(index=False):
        p = C.PRODUCTS[s.grade]
        coffee_customer = s.customer_id in ("C01", "C04", "C05", "C06") and p["coffee_test"]
        causes = {}
        for letter in s.mixes.split(","):
            r = q.loc[(s.batch_no, letter)]
            causes["Off-flavor tengik"] = max(causes.get("Off-flavor tengik", 0), 0.3 * min(1, r["oxid_intensity"]))
            if coffee_customer and not pd.isna(r["feather_fail_p"]):
                causes["Feathering di kopi"] = max(causes.get("Feathering di kopi", 0), 0.25 * r["feather_fail_p"])
            lim = spec_on(s.grade, "moisture_max", r["prod_date"])
            if r["moisture"] > lim - 0.25 and is_wet(s.ship_date):
                causes["Caking / menggumpal"] = 0.08
            if r["burnt_intensity"] > 0.25:
                causes["Bintik hitam"] = 0.12
            if r["lat_creamy"] < -0.6:
                causes["Kurang creamy"] = max(causes.get("Kurang creamy", 0), 0.06)
        causes["Kemasan / lain-lain"] = 0.004
        hit = [c for c, pr in causes.items() if rng.random() < pr]
        if not hit:
            continue
        cat = max(hit, key=lambda c: causes[c])
        delay = rng.gamma(3, 8) if cat == "Off-flavor tengik" else rng.gamma(2, 4)
        recv = pd.Timestamp(s.ship_date) + timedelta(days=float(delay))
        if recv > end:
            continue
        n += 1
        justified = True if cat != "Kemasan / lain-lain" else bool(rng.random() < 0.5)
        if cat == "Kurang creamy":
            justified = bool(rng.random() < 0.6)
        rows.append(dict(
            complaint_id=f"CMP-{recv:%y}-{n:03d}", received_date=recv.date(), customer_id=s.customer_id,
            customer_name=s.customer_name, do_no=s.do_no, batch_no=s.batch_no, grade=s.grade, category=cat,
            description=str(rng.choice(COMPLAINT_TEXT[cat])), qty_affected_kg=int(rng.integers(1, 40) * 25),
            justified=justified, status="Open" if (end - recv).days < 21 else "Closed",
        ))
    return pd.DataFrame(rows)


def recall_complaints(ship, final, micro_df, start_n):
    # urgent releases that later failed micro become formal complaints from the customer lab
    rec = final[final["final_status"] == "RECALL"]["mix_id"].str.rsplit("-", n=1).str[0].unique()
    rows = []
    n = start_n
    for b in rec:
        s = ship[ship["batch_no"] == b]
        if s.empty:
            continue
        s = s.iloc[0]
        mi = micro_df.set_index("batch_no").loc[b]
        n += 1
        recv = pd.Timestamp(s["ship_date"]) + timedelta(days=6)
        rows.append(dict(
            complaint_id=f"CMP-{recv:%y}-{n:03d}", received_date=recv.date(), customer_id=s["customer_id"],
            customer_name=s["customer_name"], do_no=s["do_no"], batch_no=b, grade=s["grade"], category="Mikro",
            description=f"Hasil uji mikro lab customer TPC {int(mi['tpc_cfu_g'] * 1.3)} cfu/g, melebihi spesifikasi",
            qty_affected_kg=int(s["qty_kg"]), justified=True, status="Closed",
        ))
    return pd.DataFrame(rows)
