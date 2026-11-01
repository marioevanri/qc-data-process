# SPOILER: this file is part of the answer key. Skip it until your detector is scored.
# Product recipes held by RND. QC never gets this table: it is written to data/truth only,
# and every formula change below is unannounced, so QC data only shows the effects.
#
# Recipes are % of dry solids. Base recipes are derived from the product targets so that
# recipe and composition agree (fat and protein in the powder = recipe x (100 - moisture) / 100).

from datetime import date, timedelta

import pandas as pd

import config as C

PROTEIN_IN = {"RM-CAS": 0.91, "RM-SMP": 0.35}
FAT_IN_SMP = 0.01


def base_recipe(grade):
    p = C.PRODUCTS[grade]
    dry = 100 / (100 - p["moisture"])
    cas = p["protein_src"] == "RM-CAS"
    r = dict(emulsifier="MDG" if cas else "Lecithin", emulsifier_pct=0.6 if cas else 0.3,
             dkp_pct=0.15 if cas else 0.0, sio2_pct=(0.5 if p["segment"] == "Retail" else 0.3) if cas else 0.0)
    prot = p["protein"] * dry / PROTEIN_IN[p["protein_src"]]
    r["caseinate_pct"] = prot if cas else 0.0
    r["smp_pct"] = 0.0 if cas else prot
    # MDG is a lipid and shows up in the fat test, lecithin is too small to matter
    r["oil_pct"] = p["fat"] * dry - (r["emulsifier_pct"] if cas else 0) - r["smp_pct"] * FAT_IN_SMP
    r["gss_pct"] = 100 - r["oil_pct"] - r["caseinate_pct"] - r["smp_pct"] - r["emulsifier_pct"] - r["dkp_pct"] - r["sio2_pct"]
    return r


# Unannounced formula changes, built from the incidents drawn for this seed (events.py).
# delta values are percentage points of the dry recipe. GSS absorbs the difference so the recipe adds up to 100.

def changes():
    out = []
    for e in C.EVENTS:
        if e["kind"] == "rnd_trial":
            out.append(dict(grade=e["grade"], event=e["id"], kind="rnd_trial", delta=e["delta"],
                            emulsifier=e["emulsifier"], suffix="T01",
                            note=f"trial RND: body lebih tebal, hanya beberapa mix di {e['line']}"))
        elif e["kind"] == "silent_reformulation_costdown":
            src = "caseinate" if "caseinate_pct" in e["delta"] else "SMP"
            out.append(dict(grade=e["grade"], event=e["id"], kind="reformulation", delta=e["delta"], emulsifier=None,
                            note=f"cost-down: sebagian {src} diganti GSS, protein turun tapi masih dalam spek"))
        elif e["kind"] == "silent_reformulation_dkp":
            for g in e["grade"].split(", "):
                out.append(dict(grade=g, event=e["id"], kind="reformulation", delta=e["delta"], emulsifier=None,
                                note="DKP dinaikkan untuk stabilitas di kopi"))
    return out


def apply(base, ch):
    r = dict(base)
    for k, v in ch["delta"].items():
        r[k] += v
        r["gss_pct"] -= v
    if ch["emulsifier"]:
        r["emulsifier"] = ch["emulsifier"]
    return r


def pick_trial_mixes(mixes, ev):
    # first day from the trial's start where its line runs its grade with enough mixes, a few consecutive ones
    n = ev.get("n_mixes", 4)
    m = mixes[(mixes["line"] == ev["line"]) & (mixes["grade"] == ev["grade"])]
    for d in pd.date_range(ev["start"], ev["start"] + timedelta(days=60)):
        day = m[m["prod_date"] == d.date()].sort_values("start")
        if len(day) >= n + 1:
            ev["start"], ev["end"] = d.date(), d.date() + timedelta(days=1)
            return list(day["mix_id"].iloc[1:1 + n])
    return []


def assign(mixes):
    # formula version used by each mix, plus the version table for data/truth
    events = {e["id"]: e for e in C.EVENTS}
    version = {g: f"{g}-v1" for g in C.PRODUCTS}
    rows = []
    for g in C.PRODUCTS:
        rows.append(dict(version=f"{g}-v1", grade=g, kind="standard", valid_from=C.START_DATE, valid_to=None,
                         applies_to="semua mix", note="formula awal", **base_recipe(g)))

    out = mixes[["mix_id", "grade", "prod_date"]].copy()
    out["formula_version"] = out["grade"] + "-v1"
    current = {g: base_recipe(g) for g in C.PRODUCTS}
    n_ver = {g: 1 for g in C.PRODUCTS}
    for ch in sorted(changes(), key=lambda c: events[c["event"]]["start"]):
        ev = events[ch["event"]]
        g = ch["grade"]
        if ch["kind"] == "rnd_trial":
            ch["version"] = f"{g}-{ch['suffix']}"
            ids = pick_trial_mixes(mixes, ev)
            if not ids:
                continue
            out.loc[out["mix_id"].isin(ids), "formula_version"] = ch["version"]
            applies = ", ".join(ids)
            recipe = apply(current[g], ch)
            valid_from, valid_to = ev["start"], ev["end"]
        else:
            n_ver[g] += 1
            ch["version"] = f"{g}-v{n_ver[g]}"
            mask = (out["grade"] == g) & (out["prod_date"] >= ev["start"])
            out.loc[mask, "formula_version"] = ch["version"]
            prev = version[g]
            rows = [dict(r, valid_to=ev["start"]) if r["version"] == prev else r for r in rows]
            recipe = apply(current[g], ch)
            current[g] = recipe
            version[g] = ch["version"]
            applies = "semua mix"
            valid_from, valid_to = ev["start"], None
        rows.append(dict(version=ch["version"], grade=g, kind=ch["kind"], valid_from=valid_from, valid_to=valid_to,
                         applies_to=applies, note=ch["note"], **recipe))

    table = pd.DataFrame(rows)
    num = [c for c in table.columns if c.endswith("_pct")]
    table[num] = table[num].round(2)
    return out[["mix_id", "formula_version"]], table


def effects(version, table):
    # how a mix's recipe differs from the grade's original recipe, in terms the quality model uses
    r = table.loc[version]
    g = r["grade"]
    b = base_recipe(g)
    p = C.PRODUCTS[g]
    cas = p["protein_src"] == "RM-CAS"
    prot_new = r["caseinate_pct"] if cas else r["smp_pct"]
    prot_old = b["caseinate_pct"] if cas else b["smp_pct"]
    fat_new = r["oil_pct"] + (r["emulsifier_pct"] if cas else 0) + r["smp_pct"] * FAT_IN_SMP
    fat_old = b["oil_pct"] + (b["emulsifier_pct"] if cas else 0) + b["smp_pct"] * FAT_IN_SMP
    return dict(
        fat_shift=(fat_new - fat_old) * (100 - p["moisture"]) / 100,
        protein_factor=prot_new / prot_old,
        smp_factor=(r["smp_pct"] / b["smp_pct"]) if not cas else 1.0,
        gss_delta=r["gss_pct"] - b["gss_pct"],
        dkp_delta=r["dkp_pct"] - b["dkp_pct"],
        datem="DATEM" in str(r["emulsifier"]),
    )
