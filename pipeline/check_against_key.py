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
}


def check(name, key, tolerance):
    with sqlite3.connect(DB_PATH) as con:
        mine = pd.read_sql(f"SELECT * FROM {name}", con)
    truth = pd.read_csv(KEY_DIR / f"{name}.csv")
    keys = [key] if isinstance(key, str) else key
    for col in keys:
        mine[col], truth[col] = mine[col].astype(str), truth[col].astype(str).replace({"True": "1", "False": "0"})
    both = mine.merge(truth, on=keys, suffixes=("", "_kunci"))

    print(f"\n{name}")
    print(f"  baris: hasil {len(mine)}, kunci {len(truth)}, {' + '.join(keys)} yang cocok {len(both)}")
    print(f"  {'kolom':<16}{'cocok':>8}{'beda':>7}{'kosong':>8}")
    for col in truth.columns:
        if col in keys or col not in mine.columns:
            continue
        a, b = both[col], both[f"{col}_kunci"]
        # empty in the key too means there was nothing to measure, that's not a gap
        both_empty = a.isna() & b.isna()
        empty = a.isna() & ~both_empty
        if col in tolerance:
            same = (a - b).abs() <= tolerance[col] + 1e-9
        elif col in ("start", "end", "sample_time", "test_time"):
            # the sheet only has hours and minutes
            same = (pd.to_datetime(a) - pd.to_datetime(b)).abs() <= pd.Timedelta(minutes=1)
        else:
            same = a.astype(str) == b.astype(str)
        same = (same | both_empty) & ~empty
        print(f"  {col:<16}{int(same.sum()):>8}{int((~same & ~empty).sum()):>7}{int(empty.sum()):>8}")


if __name__ == "__main__":
    for table, settings in CHECKS.items():
        check(table, **settings)
