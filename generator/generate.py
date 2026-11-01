# Run this file to build the whole synthetic factory:
#   python generate.py              (default seed and dates from config.py)
#   python generate.py --seed 7     (different random factory, same rules)
#
# Output:
#   data/raw/    messy files the way different departments would export them
#   data/clean/  the same records, recorded correctly (answer key for your cleaning pipeline)
#   data/truth/  hidden events, formulas and true values (answer key for early warning, never use as features)
#   docs/        text documents for RAG (SOP, specs, NCR, logbook, meeting notes, memos)

import argparse
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

import config as C
import documents as D
import events as E
import formula as F
import mess as M
import outbound as O
import quality as Q
import simulate as S

OUT = Path(__file__).parent


def build(seed):
    E.apply(seed)  # draws this factory's hidden incidents, don't print them
    rng = np.random.default_rng(seed)
    t0 = time.time()

    def step(msg):
        print(f"  {time.time() - t0:6.1f}s  {msg}")

    rec, lot_truth = S.simulate_receiving(rng); step("raw material receiving")
    mixes = S.simulate_schedule(rng); step(f"mix schedule ({len(mixes)} mixes)")
    mixes = S.assign_lots(mixes, rec, rng); step("lot traceability")
    mix_formula, ftable = F.assign(mixes); step("formula versions (hidden from QC)")
    proc = S.simulate_process(mixes, rng)
    logger = S.simulate_logger(mixes, proc, rng); step("process and dryer logger")
    mq = Q.mix_quality(mixes, proc, lot_truth, rng, mix_formula, ftable)
    samples = Q.build_samples(mixes, mq, rng); step(f"samples ({len(samples)})")
    lab = Q.lab_results(samples, mixes, mq, rng)
    lab = O.add_retests(lab, samples, rng); step("KimFis chem-phys lab")
    controls = Q.build_controls(mixes, mq, rng)
    kim = Q.sensory_kimfis(samples, controls, rng)
    ver = Q.sensory_verifikator(samples, kim, controls, rng); step("sensory KimFis + verifikator")
    nres, nspec = Q.nirs(samples, mixes, mq, controls, rng); step("NIRS scans")
    trn, trn_truth = O.retail_transitions(mixes, rng)
    mic = O.micro(mixes, rng)
    hist, final = O.release_decisions(mixes, O.final_lab(lab), kim, ver, mic, rng); step("micro and release")
    ship = O.shipments(mixes, final, rng)
    cmp = O.complaints(ship, mixes, mq, samples, rng)
    cmp = pd.concat([cmp, O.recall_complaints(ship, final, mic, len(cmp))], ignore_index=True)
    cmp = cmp.sort_values("received_date").reset_index(drop=True); step("shipments and complaints")

    mix_log = mixes.merge(proc, on="mix_id")
    clean = dict(
        master_products=master_products(),
        master_suppliers=pd.DataFrame([dict(supplier_id=k, **v) for k, v in C.SUPPLIERS.items()]),
        master_materials=pd.DataFrame([dict(material_code=k, material_name=v["name"]) for k, v in C.MATERIALS.items()]),
        master_customers=pd.DataFrame([dict(customer_id=k, name=v["name"], segment=v["segment"],
                                            grades=",".join(v["grades"])) for k, v in C.CUSTOMERS.items()]),
        master_staff=master_staff(),
        rm_receiving=rec,
        production_mix_log=mix_log[["mix_id", "batch_no", "prod_date", "line", "grade", "mix_letter", "shift",
                                    "start", "end", "mix_kg", "oil_lot", "gss_lot", "protein_lot", "inlet_temp",
                                    "outlet_temp_read", "homog_p1_read", "homog_p2_read", "feed_solids",
                                    "emulsion_temp"]].rename(columns={"outlet_temp_read": "outlet_temp",
                                                                      "homog_p1_read": "homog_p1_bar",
                                                                      "homog_p2_read": "homog_p2_bar"}),
        dryer_logger=logger,
        qc_lab_kimfis=lab,
        nirs_results=nres,
        sensory_kimfis=kim,
        sensory_verifikator=ver,
        sensory_controls=controls[["control_id", "grade", "source_batch", "start_use", "due_date", "end_use",
                                   "extended", "note"]],
        retail_transition_samples=trn.drop(columns=["true_contamination"]),
        micro_results=mic,
        release_history=hist,
        shipments=ship,
        complaints=cmp,
    )
    truth = dict(
        events=events_table(),
        lot_truth=lot_truth,
        formulation_versions=ftable,
        mix_formula=mix_formula,
        mix_truth=mixes[["mix_id", "batch_no", "prod_date", "line", "grade"]].merge(proc, on="mix_id").merge(mq, on="mix_id"),
        sample_truth=samples,
        control_truth=controls,
        transition_truth=trn[["transition_id", "sample_seq", "true_contamination"]].merge(trn_truth, on="transition_id"),
        final_status=final,
    )
    return clean, truth, nspec, rng


def events_table():
    df = pd.DataFrame(C.EVENTS)
    if "delta" in df:
        df["delta"] = df["delta"].map(lambda d: "" if not isinstance(d, dict) else ", ".join(f"{k} {v:+}" for k, v in d.items()))
    first = ["id", "kind", "start", "end", "line", "grade", "material", "supplier", "new_supplier", "magnitude", "detail"]
    return df[[c for c in first if c in df] + [c for c in df if c not in first and c != "drawn"]]


def master_products():
    rows = []
    for g, p in C.PRODUCTS.items():
        lines = [l for l, c in C.LINES.items() if g in c["grades"]]
        s = p["spec"]
        rows.append(dict(
            grade=g, grade_code=p["code"], name=p["name"], segment=p["segment"], lines=",".join(lines),
            oil=p["oil"], protein_source=p["protein_src"], fat_target=p["fat"], protein_target=p["protein"],
            fat_min=s["fat"][0], fat_max=s["fat"][1], protein_min=s["protein_min"], moisture_max=s["moisture_max"],
            visc_min=s["visc"][0], visc_max=s["visc"][1], bulk_min=s["bulk"][0], bulk_max=s["bulk"][1],
            solubility_max=s["solub_max"], wettability_max=s["wett_max"], L_min=s["L_min"],
            ph_min=s["ph"][0], ph_max=s["ph"][1], tpc_max=s["tpc_max"], ym_max=s["ym_max"],
            coffee_test=p["coffee_test"], control_days=p["control_days"], spec_rev="A",
            valid_from=C.START_DATE, valid_to=None,
        ))
    df = pd.DataFrame(rows)
    # spec revisions become a new row, the old row gets an end date
    for r in C.SPEC_REVISIONS:
        i = df.index[(df["grade"] == r["grade"]) & df["valid_to"].isna()][0]
        new = df.loc[i].copy()
        df.loc[i, "valid_to"] = r["effective"]
        new[r["param"]] = r["new"]
        new["spec_rev"] = r["rev"]
        new["valid_from"] = r["effective"]
        df = pd.concat([df, new.to_frame().T], ignore_index=True)
    return df


def master_staff():
    rows = [dict(staff_id=k, name=v["name"], role="Analis KimFis", start=v["start"], end=v["end"])
            for k, v in C.KIMFIS_ANALYSTS.items()]
    rows += [dict(staff_id=k, name=v["name"], role="Verifikator Sensory", start=None, end=None)
             for k, v in C.VERIFIKATORS.items()]
    rows += [dict(staff_id=f"RM0{i + 1}", name=n, role="QC Bahan Baku", start=None, end=None)
             for i, n in enumerate(S.RM_INSPECTORS)]
    rows += [dict(staff_id="SPV01", name=O.QC_SPV, role="QC Supervisor", start=None, end=None),
             dict(staff_id="MGR01", name=O.QA_MGR, role="QA Manager", start=None, end=None)]
    return pd.DataFrame(rows)


def write(clean, truth, nspec, raw_files, docs):
    for sub in ("data", "docs"):
        if (OUT / sub).exists():
            shutil.rmtree(OUT / sub)
    for name, df in clean.items():
        p = OUT / "data" / "clean" / f"{name}.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(p, index=False)
    clean_spec = OUT / "data" / "clean" / "nirs_spectra.csv.gz"
    nspec.to_csv(clean_spec, index=False, compression="gzip")
    for name, df in truth.items():
        p = OUT / "data" / "truth" / f"{name}.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(p, index=False)
    for rel, content in raw_files.items():
        p = OUT / "data" / "raw" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, pd.DataFrame):
            comp = "gzip" if rel.endswith(".gz") else None
            content.to_csv(p, index=False, compression=comp)
        else:
            p.write_text(content, encoding="utf-8")
    for rel, text in docs.items():
        p = OUT / "docs" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=C.SEED)
    args = ap.parse_args()
    print(f"Building {C.COMPANY} (fictional), {C.START_DATE} to {C.END_DATE}, seed {args.seed}")
    print("  hidden incidents are drawn from the seed and written to data/truth only")
    clean, truth, nspec, rng = build(args.seed)
    trial = truth["mix_formula"]
    trial_versions = truth["formulation_versions"].query("kind == 'rnd_trial'")["version"]
    trial = trial[trial["formula_version"].isin(trial_versions)]["mix_id"]
    raw_files, row_map = M.make_raw(clean, nspec, rng, trial_mixes=trial)
    truth["raw_row_map"] = row_map
    print("  messy raw layer done")
    docs = D.make_docs(clean, truth, rng)
    print(f"  {len(docs)} documents for RAG")
    write(clean, truth, nspec, raw_files, docs)
    print("Done. See data/ and docs/")


if __name__ == "__main__":
    main()
