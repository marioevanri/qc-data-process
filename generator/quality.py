# Product quality: true composition per mix and per sample, what the KimFis lab measures,
# NIRS scans, sensory reference controls, KimFis sensory and the verifikator H+1 check.

from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd

import config as C
import formula as F
from simulate import LINE_PROCESS, get_event, is_active, is_wet, progress, shift_of, sigmoid


# 1. True quality of each mix

def mix_quality(mixes, proc, lots_truth, rng, mix_formula, ftable):
    lt = lots_truth.set_index("internal_lot")
    ft = ftable.set_index("version")
    fx = {v: F.effects(v, ft) for v in ft.index}
    m = mixes.merge(proc, on="mix_id").merge(mix_formula, on="mix_id")
    rows = []
    for r in m.itertuples(index=False):
        p = C.PRODUCTS[r.grade]
        lp = LINE_PROCESS[r.line]
        d = r.prod_date
        oil, gss, pr = lt.loc[r.oil_lot], lt.loc[r.gss_lot], lt.loc[r.protein_lot]
        is_cas = p["protein_src"] == "RM-CAS"
        f = fx[r.formula_version]

        # dfat = deviation from the grade's original fat target, recipe changes included
        dfat = rng.normal(0, 0.30) + f["fat_shift"]
        if rng.random() < 0.01:  # dosing slip at the mixing tank
            dfat += rng.choice([-1, 1]) * rng.uniform(1.2, 2.0)
        fat = p["fat"] + dfat
        if is_cas:
            protein = p["protein"] * f["protein_factor"] * pr.protein / 91.0 + rng.normal(0, 0.06)
        else:
            protein = p["protein"] * f["protein_factor"] * pr.protein / 35.0 + rng.normal(0, 0.25)
        func = pr.func
        outlet = r.outlet_temp_true
        hot = outlet - lp["outlet"]

        moisture = (p["moisture"] - 0.12 * hot + 0.04 * (r.feed_solids - lp["feed"])
                    + (0.15 if is_wet(d) else 0.0) + rng.normal(0, 0.12))
        d43 = 0.85 * (lp["hp1"] / r.homog_p1_true) ** 0.5 / r.homog_eff ** 1.6 * np.exp(rng.normal(0, 0.05))
        glob = d43 / 0.85 - 1
        visc_rel = (1 + 0.35 * (protein / p["protein"] - 1) + 0.6 * (func - 1) - 0.06 * glob
                    + 0.01 * dfat + rng.normal(0, 0.025))
        ev_sc = get_event("silent_supplier_change")
        new_cas = is_cas and ev_sc["drawn"] and pr.supplier_id == ev_sc["new_supplier"]
        bulk = (p["bulk"] + 0.010 * (r.feed_solids - lp["feed"]) - 0.008 * hot - 0.002 * dfat
                + (0.005 if is_wet(d) else 0) - (0.008 if new_cas else 0) + rng.normal(0, 0.010))
        base_sol = 0.15 if is_cas else 0.35
        solub = (base_sol * np.exp(rng.normal(0, 0.25)) + 0.06 * max(0, hot - 1.5) ** 1.3
                 + (0.6 * max(0, 1 - func) if is_cas else 0.5 * max(0, 1 - func)))
        wett = max(5, (25 if is_cas else 40) + 0.9 * dfat + 25 * glob + rng.normal(0, 4))
        L = (94.5 if is_cas else 92.5) - 0.35 * max(0, hot - 1) ** 1.2 + rng.normal(0, 0.3)
        ph = p["ph"] + (0.3 * (pr.ph - 6.75) if is_cas else 0) + 1.0 * f["dkp_delta"] + rng.normal(0, 0.05)
        if p["coffee_test"]:
            # DKP buffers the coffee acid, DATEM helps the emulsion survive hot coffee
            feather_p = sigmoid(-4.6 + 50 * max(0, 0.97 - func) + 4 * glob + 6 * max(0, 6.85 - ph)
                                - 8 * f["dkp_delta"] - (0.6 if f["datem"] else 0))
        else:
            feather_p = np.nan

        # off-flavor drivers (intensity roughly 0 to 1)
        oxid = max(0, oil.pv - 1.4) * 1.8
        if rng.random() < 0.003:
            oxid = max(oxid, rng.uniform(0.5, 1.0))
        burnt = max(0, hot - 2.5) * 0.30

        # sensory latent, in scale steps, relative to the grade's ideal product
        u_c = rng.normal(0, 0.09)
        creamy = 0.25 * dfat + 3.0 * (visc_rel - 1) - 0.9 * glob + 2.5 * (func - 1) + u_c
        mouthfeel = (0.18 * dfat + 3.5 * (visc_rel - 1) - 0.6 * glob + 3.0 * (func - 1)
                     + 0.6 * u_c + rng.normal(0, 0.08))
        milky = (0.12 * dfat + (3.0 * (func - 1) if not is_cas else 0) + 6.0 * (f["smp_factor"] - 1)
                 + rng.normal(0, 0.11))
        sweet = 0.12 * (gss.de - 30) - 0.04 * dfat + 0.09 * f["gss_delta"] + rng.normal(0, 0.10)

        rows.append(dict(
            mix_id=r.mix_id, fat=fat, protein=protein, moisture=moisture, d43_um=d43, visc=p["visc_base"] * visc_rel,
            bulk=bulk, solubility=solub, wettability=wett, L_star=L, ph=ph, feather_fail_p=feather_p,
            caseinate_func=func if is_cas else np.nan, smp_func=func if not is_cas else np.nan,
            oxid_intensity=oxid, burnt_intensity=burnt,
            lat_creamy=creamy, lat_mouthfeel=mouthfeel, lat_milky=milky, lat_sweetness=sweet,
        ))
    return pd.DataFrame(rows)


# 2. Samples: three points per mix (1 start, 2 middle, 3 end)

def build_samples(mixes, mq, rng):
    m = mixes.merge(mq, on="mix_id")
    rows = []
    for r in m.itertuples(index=False):
        p = C.PRODUCTS[r.grade]
        dur = r.end - r.start
        contam1 = 0.0
        if r.after_grade_change and rng.random() < 0.35:
            contam1 = rng.uniform(0.02, 0.2)
        for point, frac in ((1, 0.08), (2, 0.5), (3, 0.9)):
            t = r.start + dur * (frac + rng.uniform(-0.03, 0.03))
            c = contam1 if point == 1 else (contam1 * 0.15 if point == 2 else 0.0)
            fat = r.fat + rng.normal(0, 0.12)
            protein = r.protein + rng.normal(0, 0.04 if p["protein_src"] == "RM-CAS" else 0.15)
            if c > 0:
                pp = C.PRODUCTS[r.prev_grade]
                fat = (1 - c) * fat + c * pp["fat"]
                protein = (1 - c) * protein + c * pp["protein"]
            moisture = r.moisture + rng.normal(0, 0.08) + (0.08 if point == 1 else 0)
            visc = r.visc * (1 + rng.normal(0, 0.02))
            brix = C.RECON_CONC_PCT * (100 - fat - moisture) / 100 * 0.92 + rng.normal(0, 0.06)
            rows.append(dict(
                sample_uid=f"{r.mix_id}{point}", mix_id=r.mix_id, batch_no=r.batch_no, line=r.line,
                grade=r.grade, prod_date=r.prod_date, mix_letter=r.mix_letter, point=point,
                sample_code=f"{r.mix_letter}{point}", sample_time=t.round("min"),
                contamination=c, fat=fat, protein=protein, moisture=moisture, visc=visc, brix=brix,
                bulk=r.bulk + rng.normal(0, 0.006),
                lat_creamy=r.lat_creamy + rng.normal(0, 0.06),
                lat_mouthfeel=r.lat_mouthfeel + rng.normal(0, 0.06),
                lat_milky=r.lat_milky + rng.normal(0, 0.05),
                lat_sweetness=r.lat_sweetness + rng.normal(0, 0.05),
                oxid_intensity=r.oxid_intensity, burnt_intensity=r.burnt_intensity,
                mixgrade_intensity=c * 4,
            ))
    return pd.DataFrame(rows)


# 3. Who is on shift

def kimfis_on_shift(ts):
    d = ts.date() if hasattr(ts, "date") else ts
    # night shift after midnight still belongs to yesterday's roster
    if ts.hour < 7:
        d = d - timedelta(days=1)
    active = [k for k, a in C.KIMFIS_ANALYSTS.items()
              if (a["start"] is None or d >= a["start"]) and (a["end"] is None or d <= a["end"])]
    w = (d - C.START_DATE).days // 7
    s = shift_of(ts)
    return active[(w + (s - 1) * 2) % len(active)]


def analyst_noise(code, d):
    a = C.KIMFIS_ANALYSTS[code]
    if a.get("training_until") and d < a["training_until"]:
        return a["training_noise"]
    return a["noise"]


# 4. KimFis chem-phys lab results (what gets typed into the lab sheet)

def lab_results(samples, mixes, mq, rng):
    ev_v = get_event("viscometer_drift")
    s = samples.merge(mixes[["mix_id", "shift"]], on="mix_id").merge(
        mq[["mix_id", "solubility", "wettability", "L_star", "ph", "feather_fail_p"]], on="mix_id")
    rows = []
    for r in s.itertuples(index=False):
        p = C.PRODUCTS[r.grade]
        test_time = (r.sample_time + timedelta(minutes=int(rng.integers(20, 150)))).round("min")
        d = test_time.date()
        vf = 1 + ev_v["magnitude"] * progress(ev_v, d) if is_active(ev_v, d) else 1.0
        analyst = kimfis_on_shift(test_time)
        row = dict(
            sample_uid=r.sample_uid, batch_no=r.batch_no, line=r.line, grade=r.grade, prod_date=r.prod_date,
            sample_code=r.sample_code, sample_time=r.sample_time, test_time=test_time, analyst_id=analyst,
            moisture_pct=round(r.moisture + rng.normal(0, 0.06), 2),
            viscosity_cp=round(r.visc * vf + rng.normal(0, 0.06), 2),
            brix=round(r.brix + rng.normal(0, 0.05), 1),
        )
        if r.point == 2:
            row["fat_pct"] = round(r.fat + rng.normal(0, 0.15), 2)
            # protein only on the day shift, nobody runs Kjeldahl at night
            day_shift = 7 <= test_time.hour < 15
            row["protein_pct"] = round(r.protein + rng.normal(0, 0.05 if p["protein_src"] == "RM-CAS" else 0.2), 2) if day_shift else np.nan
            row["bulk_density"] = round(r.bulk + rng.normal(0, 0.005), 3)
            row["solubility_ml"] = round(max(0.0, r.solubility + rng.normal(0, 0.03)), 2)
            row["wettability_s"] = int(max(3, r.wettability + rng.normal(0, 3)))
            row["L_star"] = round(r.L_star + rng.normal(0, 0.15), 1)
            row["ph"] = round(r.ph + rng.normal(0, 0.03), 2)
            if p["coffee_test"]:
                row["coffee_test"] = "Fail" if rng.random() < r.feather_fail_p else "Pass"
        rows.append(row)
    return pd.DataFrame(rows)


# 5. Sensory reference controls (the daily "0" everyone compares against)

def build_controls(mixes, mq, rng):
    # A new control is picked from recent production: the mix that tastes closest to the
    # outgoing control. So when production shifts for good, the reference slowly follows it.
    ev = get_event("control_overdue")
    lat_cols = [f"lat_{a}" for a in ATTRS]
    m = mixes[["mix_id", "batch_no", "grade", "prod_date"]].merge(mq, on="mix_id")
    rows = []
    for grade, p in C.PRODUCTS.items():
        pool = m[m["grade"] == grade]
        d = C.START_DATE - timedelta(days=int(rng.integers(0, p["control_days"])))
        cur = {a: rng.normal(0, 0.05) for a in ATTRS}
        comp = dict(fat=p["fat"], moisture=p["moisture"], protein=p["protein"], bulk=p["bulk"])
        src_batch = f"{(d - timedelta(days=4)):%y%m%d}{p['code']}P1"
        k = 0
        while d <= C.END_DATE:
            k += 1
            if k > 1:
                cand = pool[(pool["prod_date"] < d) & (pool["prod_date"] >= d - timedelta(days=14))]
                cand = cand[cand["oxid_intensity"] + cand["burnt_intensity"] < 0.05]
                if len(cand):
                    target = np.array([cur[a] for a in ATTRS])
                    # closest to the outgoing control, but the panel also won't accept something far from the ideal
                    lat = cand[lat_cols].to_numpy()
                    dist = ((lat - target) ** 2).sum(axis=1) + 0.5 * (lat ** 2).sum(axis=1)
                    best = cand.iloc[int(np.argmin(dist))]
                    cur = {a: best[f"lat_{a}"] + rng.normal(0, 0.02) for a in ATTRS}
                    comp = dict(fat=best["fat"], moisture=best["moisture"], protein=best["protein"], bulk=best["bulk"])
                    src_batch = best["batch_no"]
            due = d + timedelta(days=p["control_days"])
            end = due
            extended, note = False, ""
            # the overdue event: the control that falls due on the event start is kept until the event end
            pivot = ev["start"] - timedelta(days=p["control_days"])
            if grade == ev["grade"] and d == pivot:
                end = ev["end"]
                extended, note = True, "kontrol baru belum tersedia, kontrol lama diperpanjang"
            elif rng.random() < 0.15:
                end = due + timedelta(days=int(rng.integers(5, 15)))
                extended, note = True, "kontrol baru belum siap"
            if grade == ev["grade"] and d < pivot < end:
                end = pivot  # replaced a bit early, which lines the next control up with the event
                extended, note = False, ""
            rows.append(dict(
                control_id=f"CTRL-{p['code']}-{k:03d}", grade=grade, source_batch=src_batch,
                start_use=d, due_date=due, end_use=end, extended=extended, note=note,
                **{f"base_{a}": cur[a] for a in ATTRS},
                ctrl_fat=comp["fat"], ctrl_moisture=comp["moisture"],
                ctrl_protein=comp["protein"], ctrl_bulk=comp["bulk"],
            ))
            d = end
    return pd.DataFrame(rows)


# how much a control fades over its whole planned life (scale steps), and how fast per day once it is past due
AGING = dict(creamy=0.09, mouthfeel=0.06, milky=0.06, sweetness=0.0)
OVERDUE = dict(creamy=0.009, mouthfeel=0.007, milky=0.005, sweetness=0.0)


def control_state(controls, grade, d):
    c = controls[(controls["grade"] == grade) & (controls["start_use"] <= d) & (controls["end_use"] > d)]
    c = c.iloc[-1]
    life = C.PRODUCTS[grade]["control_days"]
    age = (d - c["start_use"]).days
    overdue = max(0, (d - c["due_date"]).days)
    lat = {a: c[f"base_{a}"] - (fade / life) * age - OVERDUE[a] * overdue for a, fade in AGING.items()}
    return c, lat


# 6. Sensory scoring

ATTRS = ["creamy", "mouthfeel", "milky", "sweetness"]

NOTE_TEMPLATES = {
    "oxid": ["aroma tengik", "ada oily/tengik di after taste", "agak tengik", "bau minyak tengik",
             "oily, tengik samar"],
    "burnt": ["after taste gosong", "ada rasa gosong", "sedikit burnt", "bintik gosong, rasa sangit"],
    "mixgrade": ["rasa masih campur grade sebelumnya", "masih kebawa grade sebelumnya",
                 "transisi, rasa belum stabil", "campur grade lama"],
    "random": ["agak apek", "aroma asing", "rasa kurang fresh"],
}
ATTR_WORD = {"creamy": "creamy", "mouthfeel": "mouthfeel", "milky": "milky", "sweetness": "manis"}


def to_score(x, deadband):
    if abs(x) < deadband:
        return 0
    return int(np.sign(x) * (1 if abs(x) < deadband + 1.0 else 2))


def grade_from(scores, off_type):
    if off_type:
        return "TP3"
    best = max(ATTRS, key=lambda a: abs(scores[a]))
    v = scores[best]
    if v == 0:
        return "Pass"
    return f"TP{abs(v)}{'+' if v > 0 else '-'}"


def note_from(scores, off_type, rng):
    if off_type:
        return str(rng.choice(NOTE_TEMPLATES[off_type]))
    parts = []
    for a in ATTRS:
        v = scores[a]
        if v == 0:
            continue
        word = ATTR_WORD[a]
        if v == -1: parts.append(f"{word} agak kurang")
        elif v == -2: parts.append(f"{word} kurang")
        elif v == 1: parts.append(f"{word} agak lebih")
        else: parts.append(f"{word} lebih")
    return ", ".join(parts)


def score_sample(r, person, ctrl_lat, rng, noise, oxid_boost=1.0):
    scores = {}
    for a in ATTRS:
        x = getattr(r, f"lat_{a}") - ctrl_lat[a] + person["bias"] + rng.normal(0, noise)
        scores[a] = to_score(x, person["deadband"])
    off_type = None
    cands = [("oxid", r.oxid_intensity * oxid_boost), ("burnt", r.burnt_intensity),
             ("mixgrade", r.mixgrade_intensity)]
    typ, inten = max(cands, key=lambda c: c[1])
    if inten > 0 and rng.random() < person["offflavor_sens"] * (1 - np.exp(-4 * inten)):
        off_type = typ
    elif rng.random() < 0.001:
        off_type = "random"
    return scores, off_type


def sensory_kimfis(samples, controls, rng):
    rows = []
    for r in samples.itertuples(index=False):
        test_time = (r.sample_time + timedelta(minutes=int(rng.integers(30, 200)))).round("min")
        d = test_time.date()
        code = kimfis_on_shift(test_time)
        person = C.KIMFIS_ANALYSTS[code]
        ctrl, ctrl_lat = control_state(controls, r.grade, r.prod_date)
        scores, off = score_sample(r, person, ctrl_lat, rng, analyst_noise(code, d))
        rows.append(dict(
            sample_uid=r.sample_uid, batch_no=r.batch_no, line=r.line, grade=r.grade, prod_date=r.prod_date,
            sample_code=r.sample_code, sample_time=r.sample_time, test_time=test_time, analyst_id=code,
            control_id=ctrl["control_id"], **{f"score_{a}": scores[a] for a in ATTRS},
            off_flavor=off is not None, off_flavor_type=off, grade_result=grade_from(scores, off),
            notes=note_from(scores, off, rng),
        ))
    return pd.DataFrame(rows)


def verif_share(d):
    share = C.VERIF_SHARE[0][1]
    for start, s in C.VERIF_SHARE:
        if d >= start:
            share = s
    return share


def sensory_verifikator(samples, kimfis, controls, rng):
    k = kimfis.set_index("sample_uid")
    rows = []
    for r in samples.itertuples(index=False):
        kg = k.loc[r.sample_uid, "grade_result"]
        must = kg in ("TP2+", "TP2-", "TP3")
        if not must and rng.random() > verif_share(r.prod_date):
            continue
        day = r.prod_date + timedelta(days=1)
        if day.weekday() == 6:  # verifikator doesn't work Sunday, slides to Monday
            day += timedelta(days=1)
        test_time = datetime.combine(day, time(8)) + timedelta(minutes=int(rng.integers(0, 240)))
        w = (day - C.START_DATE).days // 7
        code = "VR01" if w % 2 == 0 else "VR02"
        person = C.VERIFIKATORS[code]
        _, ctrl_lat = control_state(controls, r.grade, r.prod_date)
        scores, off = score_sample(r, person, ctrl_lat, rng, person["noise"], oxid_boost=1.25)
        rows.append(dict(
            sample_uid=r.sample_uid, batch_no=r.batch_no, grade=r.grade, prod_date=r.prod_date,
            sample_code=r.sample_code, test_time=test_time, verifikator_id=code,
            **{f"score_{a}": scores[a] for a in ATTRS}, off_flavor=off is not None, off_flavor_type=off,
            grade_result=grade_from(scores, off), kimfis_grade=kg, notes=note_from(scores, off, rng),
        ))
    return pd.DataFrame(rows)


# 7. NIRS scans of the powder (hopper samples plus a control scan before each grade run)

BANDS = {
    "water": [(1450, 35, 0.010), (1940, 30, 0.018)],
    "fat": [(1210, 25, 0.0025), (1730, 22, 0.0045), (1765, 20, 0.0035), (2310, 25, 0.0055), (2350, 22, 0.0045)],
    "protein": [(1510, 30, 0.0030), (2055, 30, 0.0040), (2180, 25, 0.0045)],
    "carb": [(1585, 40, 0.0012), (2100, 40, 0.0035), (2270, 35, 0.0020)],
}


def band_matrix(wl):
    out = {}
    for comp, bands in BANDS.items():
        v = np.zeros_like(wl, dtype=float)
        for c, w, k in bands:
            v += k * np.exp(-0.5 * ((wl - c) / w) ** 2)
        out[comp] = v
    return out


def nirs(samples, mixes, mq, controls, rng):
    ev_lamp = get_event("nirs_lamp_change")
    wl = np.arange(C.NIRS_WL[0], C.NIRS_WL[1] + 1, C.NIRS_WL[2])
    bm = band_matrix(wl)
    glob = mq.set_index("mix_id")["d43_um"] / 0.85 - 1

    scans = []
    # control scans: first sample of each grade run per day and line
    s = samples.sort_values("sample_time")
    first = s.groupby(["prod_date", "line", "grade"], as_index=False).first()
    n = 0
    for r in first.itertuples(index=False):
        c, _ = control_state(controls, r.grade, r.prod_date)
        n += 1
        scans.append(dict(scan_id=f"NIR{n:07d}", scan_time=r.sample_time - timedelta(minutes=int(rng.integers(5, 25))),
                          line=r.line, grade=r.grade, prod_date=r.prod_date, sample_uid=None, is_control=True,
                          control_id=c["control_id"], moisture=c["ctrl_moisture"], fat=c["ctrl_fat"],
                          protein=c["ctrl_protein"], bulk=c["ctrl_bulk"], glob=0.0))
    for r in s.itertuples(index=False):
        n += 1
        scans.append(dict(scan_id=f"NIR{n:07d}", scan_time=r.sample_time + timedelta(minutes=int(rng.integers(5, 40))),
                          line=r.line, grade=r.grade, prod_date=r.prod_date, sample_uid=r.sample_uid, is_control=False,
                          control_id=None, moisture=r.moisture, fat=r.fat, protein=r.protein, bulk=r.bulk,
                          glob=glob[r.mix_id]))
    sc = pd.DataFrame(scans).sort_values("scan_time").reset_index(drop=True)
    sc["scan_id"] = [f"NIR{i:07d}" for i in range(1, len(sc) + 1)]  # instrument numbers scans in time order
    sc["scan_time"] = pd.to_datetime(sc["scan_time"]).dt.round("s")

    moist, fat, prot = sc["moisture"].to_numpy(), sc["fat"].to_numpy(), sc["protein"].to_numpy()
    carb = 100 - moist - fat - prot
    days = (pd.to_datetime(sc["scan_time"]) - pd.Timestamp(C.START_DATE)).dt.days.to_numpy()
    lamp = (pd.to_datetime(sc["scan_time"]).dt.date >= ev_lamp["start"]).to_numpy()
    scatter = 1 + 0.8 * (sc["bulk"].to_numpy() - 0.47) + rng.normal(0, 0.02, len(sc))
    offset = 0.18 + 0.015 * lamp + 0.004 * np.sin(days / 58) + rng.normal(0, 0.006, len(sc))
    slope = 0.12 + 0.02 * lamp + rng.normal(0, 0.004, len(sc))
    x = (wl - wl[0]) / (wl[-1] - wl[0])
    fat_factor = 1 + 0.15 * sc["glob"].to_numpy()  # bigger globules leave more free fat on the surface
    chem = (np.outer(moist, bm["water"]) + np.outer(fat * fat_factor, bm["fat"])
            + np.outer(prot, bm["protein"]) + np.outer(carb, bm["carb"]))
    spectra = offset[:, None] + np.outer(slope, x) + scatter[:, None] * chem
    spectra += rng.normal(0, 0.0004, spectra.shape)
    spectra = np.round(spectra, 5)

    # the instrument's own prediction models
    lamp_bias = lamp & (pd.to_datetime(sc["scan_time"]).dt.date < C.NIRS_BIAS_FIX_DATE).to_numpy()
    is_cas = sc["grade"].map(lambda g: C.PRODUCTS[g]["protein_src"] == "RM-CAS").to_numpy()
    sc["pred_moisture"] = np.round(moist + ev_lamp.get("bias", 0.0) * lamp_bias + rng.normal(0, 0.10, len(sc)), 2)
    sc["pred_fat"] = np.round(fat + 3.0 * (scatter - 1) + rng.normal(0, 0.35, len(sc)), 2)
    sc["pred_protein"] = np.round(prot + rng.normal(0, np.where(is_cas, 0.15, 0.40)), 2)

    results = sc[["scan_id", "scan_time", "line", "grade", "prod_date", "is_control", "control_id", "sample_uid",
                  "pred_moisture", "pred_fat", "pred_protein"]].copy()
    results["instrument"] = "NIRS DS-01"
    spec_df = pd.DataFrame(spectra, columns=[f"nm_{w}" for w in wl])
    spec_df.insert(0, "scan_id", sc["scan_id"].to_numpy())
    return results, spec_df
