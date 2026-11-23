"""Compare a cleaned table in the database with the generator's answer key.

Only possible with synthetic data: the generator keeps the true values in
generator/data/clean, so the cleaning can be scored column by column.

Usage:
    python pipeline/check_against_key.py
"""

import sqlite3

import pandas as pd

from common import DB_PATH, KEY_DIR

# table -> key column, and how far a number may be off (the raw sheets are rounded)
CHECKS = {
    "production_mix_log": dict(key="mix_id", tolerance={
        "inlet_temp": 0.06, "outlet_temp": 0.06, "homog_p1_bar": 0.51, "homog_p2_bar": 0.51,
        "feed_solids": 0.26, "emulsion_temp": 0.06, "mix_kg": 0}),
    # a retest has the same sample_uid as the first test, so the key is the pair
    "qc_lab_kimfis": dict(key=["sample_uid", "is_retest"], tolerance={
        "moisture_pct": 0.006, "viscosity_cp": 0.006, "brix": 0.06, "fat_pct": 0.006, "protein_pct": 0.006,
        "bulk_density": 0.0006, "solubility_ml": 0.006, "wettability_s": 0.6, "L_star": 0.06, "ph": 0.006}),
    # notes are free text and keep the analysts' typos on purpose
    "sensory_kimfis": dict(key="sample_uid", tolerance={}, skip=["notes"]),
    # the lab writes TPC as '1,3 x 10^2', which is rounded to 2 digits, so up to 5 % off
    "micro_results": dict(key="batch_no", tolerance={"coliform_cfu_g": 0, "ym_cfu_g": 0},
                          relative={"tpc_cfu_g": 0.05}),
    # the receipt number in the key isn't on the sheet, the internal lot is unique too.
    # The sheet rounds results to 2 decimals and tons to 10 kg.
    "rm_receiving": dict(key="internal_lot", text=["supplier_lot"], tolerance={
        **{f"{who}_{t}": 0.006 for who in ("coa", "qc") for t in ("ffa", "pv", "moisture", "de", "ph", "protein",
                                                                    "fat", "solubility")},
        "coa_color_red": 0.06, "qc_color_red": 0.06, "coa_tpc": 0, "qc_tpc": 0, "qty_kg": 5}),
    "nirs_results": dict(key="scan_id", tolerance={"pred_moisture": 0.006, "pred_fat": 0.006, "pred_protein": 0.006}),
    "dryer_logger": dict(key=["timestamp", "line"], tolerance={c: 0.06 for c in (
        "inlet_temp", "outlet_temp", "homog_p1_bar", "homog_p2_bar", "emulsion_temp", "ambient_rh")}),
    "sensory_controls": dict(key="control_id", tolerance={}),
    # the sheet has the test date only, the key has the time too
    "sensory_verifikator": dict(key="sample_uid", tolerance={}, skip=["notes"]),
    # one mix can get two statuses at the same minute, those are numbered in order
    "release_history": dict(key=["mix_id", "status_time"], tolerance={}),
    "shipments": dict(key="do_no", tolerance={"qty_kg": 0}),
    "complaints": dict(key="complaint_id", tolerance={"qty_affected_kg": 0}),
    "retail_transition_samples": dict(key=["transition_id", "sample_seq"], tolerance={}),
}

TIME_COLUMNS = ("start", "end", "sample_time", "test_time", "scan_time", "received_at")


def check(name, key, tolerance, relative=None, skip=(), text=()):
    relative = relative or {}
    with sqlite3.connect(DB_PATH) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        if not exists:
            print(f"\n{name}\n  tidak ada di database, dilewati")
            return
        mine = pd.read_sql(f"SELECT * FROM {name}", con)
    # columns like lot numbers keep their leading zeros
    truth = pd.read_csv(KEY_DIR / f"{name}.csv", dtype={c: str for c in text})
    keys = [key] if isinstance(key, str) else key
    for col in keys:
        mine[col], truth[col] = mine[col].astype(str), truth[col].astype(str).replace({"True": "1", "False": "0"})
    # a key that appears twice (two logger readings with the same time stamp) is matched
    # first with first, second with second
    mine["_n"] = mine.groupby(keys).cumcount()
    truth["_n"] = truth.groupby(keys).cumcount()
    both = mine.merge(truth, on=keys + ["_n"], suffixes=("", "_kunci"))

    print(f"\n{name}")
    print(f"  baris: hasil {len(mine)}, kunci {len(truth)}, {' + '.join(keys)} yang cocok {len(both)}")
    not_made = [c for c in truth.columns if c not in mine.columns]
    if not_made or skip:
        print(f"  tidak dinilai: {', '.join(not_made + list(skip))}")
    print(f"  {'kolom':<16}{'cocok':>8}{'beda':>7}{'kosong':>8}")
    for col in truth.columns:
        if col in keys or col == "_n" or col not in mine.columns or col in skip:
            continue
        a, b = both[col], both[f"{col}_kunci"]
        # empty in the key too means there was nothing to measure, that's not a gap
        both_empty = a.isna() & b.isna()
        empty = a.isna() & ~both_empty
        if col in tolerance:
            same = (a - b).abs() <= tolerance[col] + 1e-9
        elif col in relative:
            same = (a - b).abs() <= relative[col] * b.abs() + 1e-9
        elif col in TIME_COLUMNS:
            # the sheet only has hours and minutes
            same = (pd.to_datetime(a) - pd.to_datetime(b)).abs() <= pd.Timedelta(minutes=1)
        else:
            # SQLite stores True/False as 1/0, and a column of 1/0 with gaps comes back as 1.0/0.0
            b_text = b.astype(str).replace({"True": "1", "False": "0"})
            a_num, b_num = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b_text, errors="coerce")
            same = (a.astype(str) == b_text) | (a_num.notna() & (a_num == b_num))
        same = (same | both_empty) & ~empty
        print(f"  {col:<16}{int(same.sum()):>8}{int((~same & ~empty).sum()):>7}{int(empty.sum()):>8}")


if __name__ == "__main__":
    for table, settings in CHECKS.items():
        check(table, **settings)
