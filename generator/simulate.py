# Builds the clean (correctly recorded) factory data plus the hidden truth tables.
# Nothing here is messy on purpose, mess.py dirties the data afterwards.
# Flow: receiving -> mix schedule -> process -> product quality -> lab, NIRS, sensory
#       -> micro -> release -> shipment -> complaints

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

import config as C


# 1. Small helpers

def days_between(a, b):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def get_event(kind):
    # the drawn incident of this kind, or an inert stand-in that is never active
    from events import inert
    return next((e for e in C.EVENTS if e["kind"] == kind), None) or inert(kind)


def is_active(ev, d):
    if isinstance(d, datetime):
        d = d.date()
    return ev["start"] <= d and (ev["end"] is None or d < ev["end"])


def progress(ev, d):
    # 0 at the start of a gradual event, 1 at its end
    total = (ev["end"] - ev["start"]).days
    return min(1.0, max(0.0, (d - ev["start"]).days / total))


def is_wet(d):
    return d.month in C.WET_MONTHS


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def spec_on(grade, param, d):
    # spec value valid on date d, after any revision
    val = C.PRODUCTS[grade]["spec"][param]
    for r in C.SPEC_REVISIONS:
        if r["grade"] == grade and r["param"] == param and d >= r["effective"]:
            val = r["new"]
    return val


# 2. Raw material receiving and incoming inspection

RM_SPECS = {
    "RM-OIL-HCO": dict(ffa_max=0.10, pv_max=2.0, moisture_max=0.10, color_red_max=3.0),
    "RM-OIL-PO": dict(ffa_max=0.10, pv_max=2.0, moisture_max=0.10, color_red_max=3.0),
    "RM-GSS": dict(de=(28.0, 32.0), moisture_max=5.0, ph=(4.5, 5.5)),
    "RM-CAS": dict(protein_min=88.0, moisture_max=6.0, ph=(6.4, 7.0)),
    "RM-SMP": dict(protein_min=34.0, moisture_max=4.0, fat_max=1.25, solubility_max=1.0, tpc_max=10000),
}

# typical quality per supplier: (mean, sd)
SUPPLIER_PROFILE = {
    "SUP01": dict(ffa=(0.04, 0.012), pv=(0.50, 0.15), moisture=(0.03, 0.01), color_red=(1.5, 0.3)),
    "SUP02": dict(ffa=(0.06, 0.015), pv=(0.80, 0.22), moisture=(0.05, 0.015), color_red=(2.0, 0.35)),
    "SUP03": dict(ffa=(0.05, 0.012), pv=(0.60, 0.18), moisture=(0.04, 0.012), color_red=(2.2, 0.3)),
    "SUP04": dict(ffa=(0.07, 0.015), pv=(0.90, 0.25), moisture=(0.05, 0.015), color_red=(2.6, 0.3)),
    "SUP05": dict(de=(30.0, 0.6), moisture=(3.8, 0.30), ph=(5.0, 0.13)),
    "SUP06": dict(de=(30.6, 0.65), moisture=(4.1, 0.30), ph=(4.85, 0.14)),
    "SUP07": dict(protein=(91.2, 0.5), moisture=(4.8, 0.35), ph=(6.78, 0.07), func=(1.00, 0.03)),
    "SUP08": dict(protein=(89.8, 0.8), moisture=(5.3, 0.40), ph=(6.62, 0.09), func=(0.95, 0.03)),
    "SUP09": dict(protein=(35.4, 0.35), moisture=(3.4, 0.15), fat=(0.90, 0.10), solubility=(0.40, 0.12),
                  func=(1.00, 0.025), tpc=(1500, 0.6)),
    "SUP11": dict(protein=(35.1, 0.40), moisture=(3.6, 0.18), fat=(0.95, 0.10), solubility=(0.60, 0.15),
                  func=(0.95, 0.03), tpc=(2200, 0.6)),
    "SUP10": dict(protein=(35.0, 0.35), moisture=(3.55, 0.15), fat=(1.00, 0.10), solubility=(0.55, 0.15),
                  func=(0.98, 0.03), tpc=(2500, 0.6)),
}

# measurement noise of the RM lab
RM_LAB_SD = dict(ffa=0.005, pv=0.06, moisture=0.01, color_red=0.15, de=0.3, ph=0.03, protein=0.3,
                 fat=0.04, solubility=0.05)

RM_INSPECTORS = ["Yusuf Hidayat", "Nadia Rahmawati"]


def draw_lot_truth(mat, sup, d, rng):
    prof = SUPPLIER_PROFILE[sup]
    t = {}
    for p, (mu, sd) in prof.items():
        if p == "tpc":
            t[p] = float(mu * rng.lognormal(0, sd))
        else:
            t[p] = float(rng.normal(mu, sd))
    for p in ("ffa", "pv", "moisture", "solubility"):
        if p in t:
            t[p] = max(t[p], 0.005)
    ev = get_event("bad_oil_lot")
    if mat == ev["material"] and sup == ev["supplier"] and is_active(ev, d):
        t["pv"] = float(rng.uniform(ev["pv_low"], ev["pv_high"]))
        t["ffa"] = float(rng.uniform(0.07, 0.095))
    return t


def rm_decision(mat, qc):
    s = RM_SPECS[mat]
    hard, cond = [], []
    if mat.startswith("RM-OIL"):
        if qc["ffa"] > s["ffa_max"]: hard.append("FFA tinggi")
        elif qc["ffa"] > 0.085: cond.append("FFA mendekati batas")
        if qc["pv"] > s["pv_max"]: hard.append("PV tinggi")
        elif qc["pv"] >= 1.5: cond.append("PV mendekati batas")
        if qc["moisture"] > s["moisture_max"]: hard.append("kadar air tinggi")
        if qc["color_red"] > s["color_red_max"]: cond.append("warna merah tinggi")
    elif mat == "RM-GSS":
        lo, hi = s["de"]
        if not lo <= qc["de"] <= hi: hard.append("DE di luar spek")
        elif not lo + 0.5 <= qc["de"] <= hi - 0.5: cond.append("DE mendekati batas")
        if qc["moisture"] > s["moisture_max"]: hard.append("kadar air tinggi")
        if not s["ph"][0] <= qc["ph"] <= s["ph"][1]: cond.append("pH di luar range")
    elif mat == "RM-CAS":
        if qc["protein"] < s["protein_min"]: hard.append("protein rendah")
        if qc["moisture"] > s["moisture_max"]: hard.append("kadar air tinggi")
        if not s["ph"][0] <= qc["ph"] <= s["ph"][1]: cond.append("pH di luar range")
    elif mat == "RM-SMP":
        if qc["protein"] < s["protein_min"]: hard.append("protein rendah")
        if qc["moisture"] > s["moisture_max"]: hard.append("kadar air tinggi")
        if qc["fat"] > s["fat_max"]: cond.append("lemak tinggi")
        if qc["solubility"] > s["solubility_max"]: cond.append("kelarutan kurang")
    if hard:
        return "Reject", "; ".join(hard + cond)
    if cond:
        return "Conditional", "; ".join(cond)
    return "Accept", ""


def simulate_receiving(rng):
    rows, truth = [], []
    cas_ev = get_event("silent_supplier_change")
    oil_ev = get_event("bad_oil_lot")
    n = 0
    for mat, m in C.MATERIALS.items():
        d = C.START_DATE - timedelta(days=21)
        seq_per_day = {}
        while d <= C.END_DATE:
            if d.weekday() == 6:  # no deliveries on Sunday
                d += timedelta(days=1)
                continue
            sups = list(m["suppliers"].keys())
            sup = rng.choice(sups, p=list(m["suppliers"].values()))
            if mat == cas_ev["material"] and d >= cas_ev["start"]:
                sup = cas_ev["new_supplier"]
            if mat == oil_ev["material"] and is_active(oil_ev, d):
                sup = oil_ev["supplier"]
            n += 1
            seq_per_day[d] = seq_per_day.get(d, 0) + 1
            short = mat.split("-")[-1]
            internal_lot = f"{short}-{d:%y%m%d}-{seq_per_day[d]:02d}"
            t = draw_lot_truth(mat, sup, d, rng)

            # supplier COA is usually a bit kinder than reality (tested at their site, before transport)
            coa, qc = {}, {}
            for p, v in t.items():
                if p == "func":
                    continue
                if p == "tpc":
                    coa[p] = round(v * rng.uniform(0.4, 0.9), -1)
                    qc[p] = float(round(v * rng.lognormal(0, 0.25), -1))
                    continue
                bias = {"pv": -0.15 * v, "ffa": -0.1 * v}.get(p, 0.0)
                coa[p] = v + bias + rng.normal(0, RM_LAB_SD.get(p, 0.01) * 0.7)
                qc[p] = v + rng.normal(0, RM_LAB_SD.get(p, 0.01))

            # GSS DE is only tested by QC on roughly every third lot
            if mat == "RM-GSS" and rng.random() > 0.35:
                qc["de"] = np.nan
            decision, reason = rm_decision(mat, {k: (coa[k] if pd.isna(qc.get(k)) else qc[k]) for k in qc})
            recv_time = datetime.combine(d, time(8)) + timedelta(minutes=int(rng.integers(0, 540)))
            release = d + timedelta(days=1 if mat != "RM-SMP" else 4)  # SMP waits for micro
            rows.append(dict(
                receipt_id=f"RCV-{n:05d}", received_at=recv_time, material_code=mat,
                material_name=m["name"], supplier_id=sup, supplier_name=C.SUPPLIERS[sup]["name"],
                supplier_lot=f"{sup[-2:]}{rng.integers(100000, 999999)}", internal_lot=internal_lot,
                qty_kg=int(rng.integers(*m["unit_lot_kg"]) // 25 * 25),
                **{f"coa_{k}": round(v, 3) for k, v in coa.items()},
                **{f"qc_{k}": (round(v, 3) if not pd.isna(v) else np.nan) for k, v in qc.items()},
                decision=decision, remarks=reason, inspector=rng.choice(RM_INSPECTORS),
                qc_release_date=release if decision != "Reject" else pd.NaT,
            ))
            truth.append(dict(internal_lot=internal_lot, material_code=mat, supplier_id=sup, **t))
            step = m["every_days"] * rng.uniform(0.7, 1.3)
            if decision == "Reject":
                step = 2  # replacement delivery
            d += timedelta(days=max(1, int(round(step))))
    rec = pd.DataFrame(rows).sort_values("received_at").reset_index(drop=True)
    return rec, pd.DataFrame(truth)


# 3. Production calendar and mix schedule

THROUGHPUT_KG_H = {"P1": 1450, "P2": 1300, "RT": 260}


def shift_of(ts):
    h = ts.hour
    if 7 <= h < 15:
        return 1
    if 15 <= h < 23:
        return 2
    return 3


def letters(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def simulate_schedule(rng):
    rows = []
    last_grade = {line: cfg["grades"][0] for line, cfg in C.LINES.items()}
    for d in days_between(C.START_DATE, C.END_DATE):
        shutdown = any(a <= d <= b for a, b in C.SHUTDOWNS) or d in C.HOLIDAYS
        for line, cfg in C.LINES.items():
            if shutdown:
                continue
            if d.weekday() == 6 and rng.random() >= cfg["runs_sunday"]:
                continue
            if rng.random() < 0.03:  # breakdown or no order that day
                continue
            n = int(rng.integers(cfg["mixes_per_day"][0], cfg["mixes_per_day"][1] + 1))
            if line == "RT":
                n_blocks = int(rng.choice([1, 2, 3], p=[0.3, 0.45, 0.25]))
            else:
                n_blocks = int(rng.choice([1, 2, 3], p=[0.4, 0.5, 0.1]))
            n_blocks = min(n_blocks, n)
            grades = cfg["grades"]
            g = last_grade[line] if rng.random() < 0.6 else rng.choice(grades)
            plan = []
            cuts = sorted(rng.choice(np.arange(1, n), size=n_blocks - 1, replace=False)) if n_blocks > 1 else []
            sizes = np.diff([0, *cuts, n])
            for bsize in sizes:
                plan += [g] * int(bsize)
                g = grades[1] if g == grades[0] else grades[0]
            last_grade[line] = plan[-1]

            t = datetime.combine(d, time(7)) + timedelta(minutes=int(rng.integers(0, 20)))
            day_end = datetime.combine(d + timedelta(days=1), time(8))
            letter_count = {}
            prev = None
            for i, grade in enumerate(plan):
                change = prev is not None and grade != prev
                if change:
                    t += timedelta(minutes=int(rng.integers(30, 60)))
                kg = int(rng.integers(*cfg["mix_kg"]) // 50 * 50)
                dur = timedelta(hours=kg / THROUGHPUT_KG_H[line] * rng.uniform(0.92, 1.1))
                if t + dur > day_end:
                    break
                batch_no = f"{d:%y%m%d}{C.PRODUCTS[grade]['code']}{line}"
                k = letter_count.get(batch_no, 0)
                letter_count[batch_no] = k + 1
                rows.append(dict(
                    mix_id=f"{batch_no}-{letters(k)}", batch_no=batch_no, prod_date=d, line=line,
                    grade=grade, mix_letter=letters(k), seq_in_day=i + 1, start=t, end=t + dur,
                    shift=shift_of(t), mix_kg=kg, after_grade_change=change,
                    first_of_day=(i == 0), prev_grade=prev,
                ))
                t += dur
                prev = grade
    return pd.DataFrame(rows)


# 4. Which raw material lot went into which mix

def assign_lots(mixes, rec, rng):
    usable = rec[rec["decision"] != "Reject"][["material_code", "internal_lot", "qc_release_date"]].copy()
    usable["qc_release_date"] = pd.to_datetime(usable["qc_release_date"])
    by_mat = {m: g.sort_values("qc_release_date") for m, g in usable.groupby("material_code")}
    oil, gss, prot = [], [], []
    for _, mx in mixes.iterrows():
        p = C.PRODUCTS[mx["grade"]]
        picks = []
        for mat in (p["oil"], "RM-GSS", p["protein_src"]):
            g = by_mat[mat]
            avail = g[g["qc_release_date"] <= pd.Timestamp(mx["prod_date"])]
            # mostly the newest released lot, sometimes leftover stock of the previous one
            if len(avail) >= 2 and rng.random() < 0.15:
                picks.append(avail.iloc[-2]["internal_lot"])
            else:
                picks.append(avail.iloc[-1]["internal_lot"])
        oil.append(picks[0]); gss.append(picks[1]); prot.append(picks[2])
    mixes = mixes.copy()
    mixes["oil_lot"], mixes["gss_lot"], mixes["protein_lot"] = oil, gss, prot
    return mixes


# 5. Process conditions per mix and the 30-minute logger

LINE_PROCESS = {
    "P1": dict(inlet=186, outlet=90.0, hp1=180, hp2=35, feed=52.0),
    "P2": dict(inlet=184, outlet=90.0, hp1=180, hp2=35, feed=52.0),
    "RT": dict(inlet=178, outlet=88.0, hp1=160, hp2=30, feed=50.0),
}


def simulate_process(mixes, rng):
    ev_dry = get_event("spray_dryer_sensor_bias")
    ev_hom = get_event("homogenizer_wear")
    ev_trial = get_event("production_trial")
    out = []
    for _, mx in mixes.iterrows():
        lp = LINE_PROCESS[mx["line"]]
        d = mx["prod_date"]
        outlet_true = rng.normal(lp["outlet"], 0.9)
        inlet = rng.normal(lp["inlet"], 2.0)
        if mx["line"] == ev_trial["line"] and is_active(ev_trial, d):
            # gas saving trial: lower inlet, the dryer settles at a cooler outlet
            inlet -= ev_trial["inlet_drop"]
            outlet_true -= ev_trial["outlet_drop"]
        sensor_bias = 0.0
        if mx["line"] == ev_dry["line"] and is_active(ev_dry, d):
            b = ev_dry["magnitude"]
            sensor_bias = -b
            outlet_true += b + rng.normal(0, 0.4)
            inlet += 1.35 * b
        outlet_read = outlet_true + sensor_bias + rng.normal(0, 0.2)
        eff = min(1.0, rng.normal(1.0, 0.015))
        if mx["line"] == ev_hom["line"] and is_active(ev_hom, d):
            eff -= ev_hom["magnitude"] * progress(ev_hom, d) + rng.normal(0, 0.02)
        hp1_true = rng.normal(lp["hp1"], 3.0)
        hp1_read = hp1_true - (1 - eff) * 12 + rng.normal(0, 1.5)
        hp2_read = rng.normal(lp["hp2"], 1.2)
        feed = rng.normal(lp["feed"], 1.2)
        month_rh = 82 if is_wet(d) else 66
        rh = float(np.clip(rng.normal(month_rh, 6), 40, 98))
        out.append(dict(
            mix_id=mx["mix_id"], inlet_temp=inlet, outlet_temp_read=outlet_read, outlet_temp_true=outlet_true,
            homog_p1_read=hp1_read, homog_p1_true=hp1_true, homog_p2_read=hp2_read, homog_eff=eff,
            feed_solids=feed, emulsion_temp=rng.normal(65, 1.5), ambient_rh=rh,
        ))
    return pd.DataFrame(out)


def simulate_logger(mixes, proc, rng):
    # one reading every 30 minutes while a mix is on the dryer
    m = mixes[["mix_id", "line", "start", "end"]].merge(proc, on="mix_id")
    rows = []
    for _, r in m.iterrows():
        t = r["start"].ceil("30min") if hasattr(r["start"], "ceil") else pd.Timestamp(r["start"]).ceil("30min")
        end = pd.Timestamp(r["end"])
        while t < end:
            rows.append(dict(
                timestamp=t, line=r["line"],
                inlet_temp=round(r["inlet_temp"] + rng.normal(0, 0.8), 1),
                outlet_temp=round(r["outlet_temp_read"] + rng.normal(0, 0.4), 1),
                homog_p1_bar=round(r["homog_p1_read"] + rng.normal(0, 1.0), 0),
                homog_p2_bar=round(r["homog_p2_read"] + rng.normal(0, 0.6), 0),
                emulsion_temp=round(r["emulsion_temp"] + rng.normal(0, 0.4), 1),
                ambient_rh=round(r["ambient_rh"] + rng.normal(0, 1.5), 0),
            ))
            t += pd.Timedelta(minutes=30)
    return pd.DataFrame(rows).sort_values(["line", "timestamp"]).reset_index(drop=True)
