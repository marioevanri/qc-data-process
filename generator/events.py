# SPOILER: this file draws the answer key. Reading its code tells you which kinds of incident
# can happen. Printing its output for your seed tells you exactly what happened, so don't.
#
# Every seed gets its own set of hidden incidents: which ones happen, when, on which line,
# grade or supplier, and how big the effect is. The QC data only shows their effects.

from datetime import date, timedelta

import numpy as np

import config as C

FAR = date(2100, 1, 1)  # start date for incidents that don't happen in this factory


def inert(kind):
    # stand-in for an incident that was not drawn, so simulation code never has to check
    return dict(id=None, kind=kind, drawn=False, start=FAR, end=FAR + timedelta(days=1), line=None, grade=None,
                material=None, supplier=None, new_supplier=None, magnitude=0.0)


def in_shutdown(d):
    return any(a <= d <= b for a, b in C.SHUTDOWNS)


EARLIEST = date(2025, 3, 15)


def pick_day(rng, lo, hi):
    # uniform day in [lo, hi], moved past a shutdown if it lands inside one
    lo = max(lo, EARLIEST)
    d = lo + timedelta(days=int(rng.integers(0, max(1, (hi - lo).days + 1))))
    while in_shutdown(d):
        d += timedelta(days=1)
    return d


def r1(x, nd=2):
    return float(round(x, nd))


def caseinate_grades():
    return [g for g, p in C.PRODUCTS.items() if p["protein_src"] == "RM-CAS"]


def lines_for(grade):
    return [l for l, c in C.LINES.items() if grade in c["grades"]]


# One builder per kind of incident. Each returns the incident with its own random details.

def ev_dryer(rng):
    line = str(rng.choice(list(C.LINES)))
    start = pick_day(rng, date(2025, 2, 15), date(2026, 4, 15))
    b = r1(rng.uniform(2.3, 3.3), 1)
    return dict(kind="spray_dryer_sensor_bias", line=line, start=start,
                end=start + timedelta(days=int(rng.integers(28, 43))), magnitude=b,
                detail=f"{line} outlet temperature sensor reads ~{b} C low, operators push inlet up, real outlet "
                       "runs hot: drier powder, darker color, poorer solubility, burnt notes when it gets hot enough")


def ev_viscometer(rng):
    start = pick_day(rng, date(2025, 2, 15), date(2026, 3, 31))
    m = r1(rng.uniform(0.08, 0.14))
    return dict(kind="viscometer_drift", start=start, end=start + timedelta(days=int(rng.integers(50, 71))), magnitude=m,
                detail=f"Lab viscometer reads progressively high, up to +{round(100 * m)} % before recalibration")


def ev_bad_oil(rng):
    mat = str(rng.choice(["RM-OIL-PO", "RM-OIL-HCO"]))
    sups = C.MATERIALS[mat]["suppliers"]
    sup = str(rng.choice(list(sups), p=list(sups.values())))
    start = pick_day(rng, date(2025, 2, 15), date(2026, 5, 10))
    lo = r1(rng.uniform(1.5, 1.6))
    grades = [g for g, p in C.PRODUCTS.items() if p["oil"] == mat]
    return dict(kind="bad_oil_lot", material=mat, supplier=sup, start=start,
                end=start + timedelta(days=int(rng.integers(4, 7))), pv_low=lo, pv_high=r1(lo + rng.uniform(0.15, 0.3)),
                grade=", ".join(grades),
                detail=f"{C.MATERIALS[mat]['name']} deliveries from {sup} with high peroxide value, accepted as "
                       "conditional. Mixes using them develop oxidized/oily off-flavor, complaints weeks later")


def ev_supplier(rng):
    mat = str(rng.choice(["RM-CAS", "RM-SMP"]))
    new = "SUP08" if mat == "RM-CAS" else "SUP11"
    old = ", ".join(C.MATERIALS[mat]["suppliers"])
    start = pick_day(rng, date(2025, 4, 1), date(2026, 2, 28))
    grades = [g for g, p in C.PRODUCTS.items() if p["protein_src"] == mat]
    return dict(kind="silent_supplier_change", material=mat, old_supplier=old, new_supplier=new, start=start, end=None,
                grade=", ".join(grades), known=min(C.END_DATE, start + timedelta(days=int(rng.integers(80, 111)))),
                memo_date=start + timedelta(days=int(rng.integers(25, 41))),
                detail=f"{C.MATERIALS[mat]['name']} supplier switched from {old} to {new} without telling QC. "
                       "The new material has lower functionality: lower viscosity, thinner body"
                       + (", more feathering failures" if mat == "RM-CAS" else ", less milky"))


def ev_homog(rng):
    line = str(rng.choice(list(C.LINES)))
    start = pick_day(rng, date(2025, 2, 15), date(2026, 4, 10))
    m = r1(rng.uniform(0.2, 0.3))
    return dict(kind="homogenizer_wear", line=line, start=start, end=start + timedelta(days=int(rng.integers(35, 56))),
                magnitude=m,
                detail=f"{line} homogenizer valve wearing out, gauge still near setpoint but efficiency drops up to "
                       f"{round(100 * m)} %: bigger fat globules, less creamy, more feathering. Fixed at overhaul")


def ev_lamp(rng):
    start = pick_day(rng, date(2025, 2, 15), date(2026, 4, 30))
    fix = min(C.END_DATE, start + timedelta(days=int(rng.integers(35, 51))))
    b = r1(rng.uniform(0.10, 0.20))
    return dict(kind="nirs_lamp_change", start=start, end=None, fix_date=fix, bias=b,
                detail=f"NIRS lamp replaced, spectral baseline and slope shift, predicted moisture biased +{b} "
                       f"until the model bias correction on {fix}")


def ev_cip(rng):
    line = str(rng.choice(list(C.LINES)))
    start = pick_day(rng, date(2025, 4, 15), date(2026, 5, 20))
    end = start + timedelta(days=int(rng.integers(4, 7)))
    rev = end + timedelta(days=int(rng.integers(21, 31)))
    return dict(kind="cip_failure", line=line, start=start, end=end, sop_rev_date=rev if rev <= C.END_DATE - timedelta(days=14) else None,
                detail=f"Incomplete CIP on {line} after a valve fault, elevated TPC in batches that week")


def ev_control(rng):
    grade = str(rng.choice(list(C.PRODUCTS)))
    days = C.PRODUCTS[grade]["control_days"]
    lo = C.START_DATE + timedelta(days=days + 15)
    start = pick_day(rng, lo, date(2026, 5, 15))
    end = min(C.END_DATE - timedelta(days=5), start + timedelta(days=int(rng.integers(28, 41))))
    return dict(kind="control_overdue", grade=grade, start=start, end=end,
                detail=f"No fresh {grade} control available, old control kept ~{(end - start).days} days past due. "
                       "The aged control makes product look 'lebih' relative to reference")


def ev_rnd_trial(rng):
    grade = str(rng.choice(list(C.PRODUCTS)))
    line = str(rng.choice(lines_for(grade)))
    start = pick_day(rng, date(2025, 2, 15), date(2026, 5, 20))
    cas = C.PRODUCTS[grade]["protein_src"] == "RM-CAS"
    delta = dict(oil_pct=r1(rng.uniform(1.2, 1.6))) if cas else dict(oil_pct=r1(rng.uniform(1.0, 1.4)))
    if cas:
        delta["dkp_pct"] = 0.10
    return dict(kind="rnd_trial", grade=grade, line=line, start=start, end=start + timedelta(days=14),
                n_mixes=int(rng.integers(3, 6)), delta=delta, emulsifier="MDG + DATEM" if cas else None,
                detail=f"RND trial {grade}-T01 on a few consecutive {line} mixes on one day (exact mixes in "
                       "mix_formula.csv): more oil" + (", MDG + DATEM, more DKP" if cas else "")
                       + ". Fat near or over the upper spec, creamy 'lebih', shipped as normal when it passed")


def ev_costdown(rng):
    grade = str(rng.choice(list(C.PRODUCTS)))
    cas = C.PRODUCTS[grade]["protein_src"] == "RM-CAS"
    start = pick_day(rng, date(2025, 4, 1), date(2026, 4, 15))
    delta = dict(caseinate_pct=-r1(rng.uniform(0.25, 0.35))) if cas else dict(smp_pct=-r1(rng.uniform(2.4, 3.2), 1))
    return dict(kind="silent_reformulation_costdown", grade=grade, start=start, end=None, delta=delta,
                detail=f"{grade} cost-down reformulation v2: part of the " + ("caseinate" if cas else "SMP")
                       + " replaced by GSS. Protein lower but still in spec, slightly lower viscosity, thinner body"
                       + ("" if cas else ", less milky, sweeter")
                       + ". The sensory control follows the new formula after one control cycle, NIRS history does not")


def ev_prod_trial(rng):
    line = str(rng.choice(list(C.LINES)))
    start = pick_day(rng, date(2025, 2, 15), date(2026, 5, 20))
    di, do = r1(rng.uniform(5, 7), 1), r1(rng.uniform(1.8, 2.6), 1)
    return dict(kind="production_trial", line=line, start=start, end=start + timedelta(days=int(rng.integers(5, 9))),
                inlet_drop=di, outlet_drop=do,
                detail=f"Production trial on {line} to save gas: inlet ~{di} C lower, real outlet ~{do} C lower. "
                       "Moisture up, bulk density up. Visible in the process log, QC not informed")


def ev_dkp(rng):
    start = pick_day(rng, date(2025, 4, 1), date(2026, 4, 30))
    dk = r1(rng.uniform(0.08, 0.12))
    return dict(kind="silent_reformulation_dkp", grade=", ".join(caseinate_grades()), start=start, end=None,
                delta=dict(dkp_pct=dk), trial_note=start - timedelta(days=int(rng.integers(25, 45))),
                detail=f"RND raised dipotassium phosphate by {dk} % in the caseinate creamers for coffee stability. "
                       "QC heard about the trial, was never told it went live. pH up, coffee test failures drop")


BUILDERS = [ev_dryer, ev_viscometer, ev_bad_oil, ev_supplier, ev_homog, ev_lamp, ev_cip, ev_control,
            ev_rnd_trial, ev_costdown, ev_prod_trial, ev_dkp]


def draw(seed):
    # separate stream so the factory's own randomness doesn't shift when this list changes
    rng = np.random.default_rng([seed, 2718])
    for _ in range(200):
        keep = [b for b in BUILDERS if rng.random() < 0.75]
        if not 7 <= len(keep) <= 11:
            continue
        evs = [b(rng) for b in keep]
        n25 = sum(e["start"].year == 2025 for e in evs)
        n26 = len(evs) - n25
        if n25 >= 3 and n26 >= 3:
            break
    evs.sort(key=lambda e: e["start"])
    for i, e in enumerate(evs, start=1):
        e["id"] = f"EV{i:02d}"
        e["drawn"] = True
        for k in ("line", "grade", "material", "supplier", "new_supplier"):
            e.setdefault(k, None)
        e.setdefault("magnitude", 0.0)
    return evs


def apply(seed):
    # puts the drawn incidents and the dates that depend on them into config
    C.EVENTS = draw(seed)
    lamp = next((e for e in C.EVENTS if e["kind"] == "nirs_lamp_change"), None)
    cip = next((e for e in C.EVENTS if e["kind"] == "cip_failure"), None)
    C.NIRS_BIAS_FIX_DATE = lamp["fix_date"] if lamp else FAR
    C.SOP_HOLD_REV05_DATE = cip["sop_rev_date"] if cip and cip["sop_rev_date"] else FAR
    return C.EVENTS
