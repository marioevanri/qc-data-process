"""Clean the production mix log: one row per mix, with the keys every other table joins on.

Columns and their raw names are in config/kolom.csv. Only prod_date, line, grade, batch_no
and start are needed, everything else (process values, lots, operator) may be missing when
production shares less with QC.
"""

import pandas as pd

from common import (SourceOff, apply_limits, clean_batch, clean_grade, clean_lot, clean_time,
                    drop_exact_duplicates, parse_date, read_source, to_number)

NUMBERS = ["mix_kg", "inlet_temp", "outlet_temp", "homog_p1_bar", "homog_p2_bar", "feed_solids", "emulsion_temp"]


def clean_production_mix_log():
    df, notes = read_source("production_mix_log")

    # 1. the same row exported twice
    df = drop_exact_duplicates(df, notes)

    # 2. text columns people type in different ways
    df["line"] = df["line"].str.strip().str.upper()
    df["grade"] = clean_grade(df["grade"])
    df["batch_no"] = clean_batch(df["batch_no"])
    for col in ["oil_lot", "gss_lot", "protein_lot"]:
        df[col] = clean_lot(df[col])

    # 3. dates and times. A production day runs 07:00 to 07:00, so a mix that starts
    #    at 02:00 belongs to the previous date but happens on the next calendar day.
    df["prod_date"] = parse_date(df["prod_date"])
    start_time = pd.to_timedelta(clean_time(df["start"]) + ":00")
    end_time = pd.to_timedelta(clean_time(df["end"]) + ":00")
    after_midnight = start_time < pd.Timedelta(hours=7)
    df["start"] = df["prod_date"] + start_time + pd.to_timedelta(after_midnight.astype(int), unit="D")
    df["end"] = df["start"].dt.normalize() + end_time
    df.loc[df["end"] < df["start"], "end"] += pd.Timedelta(days=1)
    hour = df["start"].dt.hour
    df["shift"] = 3
    df.loc[(hour >= 7) & (hour < 15), "shift"] = 1
    df.loc[(hour >= 15) & (hour < 23), "shift"] = 2

    # 4. mix letter. "Mix No" counts mixes per line per day, but the lab and sensory sheets
    #    use a letter that counts mixes inside one batch number: first mix of the batch is A.
    df = df.sort_values(["batch_no", "start"])
    order = df.groupby("batch_no").cumcount()
    df["mix_letter"] = order.map(lambda n: chr(ord("A") + n))
    df["mix_id"] = df["batch_no"] + "-" + df["mix_letter"]

    # 5. numbers, with slipped decimal points fixed by the ranges in batas_wajar.csv
    for col in NUMBERS:
        df[col] = to_number(df[col])
    df["mix_kg"] = df["mix_kg"].round().astype("Int64")
    apply_limits(df, "production_mix_log", notes)
    for col in NUMBERS[1:]:
        notes[f"kosong_{col}"] = int(df[col].isna().sum())

    df["prod_date"] = df["prod_date"].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    notes["mix_id_ganda"] = int(df["mix_id"].duplicated().sum())
    columns = ["mix_id", "batch_no", "prod_date", "line", "grade", "mix_letter", "shift", "start", "end", "mix_kg",
               "oil_lot", "gss_lot", "protein_lot", "inlet_temp", "outlet_temp", "homog_p1_bar", "homog_p2_bar",
               "feed_solids", "emulsion_temp", "operator", "remarks"]
    return df[columns].reset_index(drop=True), notes


def production_or_none():
    """The clean production log, or None when production data isn't available to QC.
    The other tables then skip the steps that need it."""
    try:
        return clean_production_mix_log()[0]
    except SourceOff:
        return None


if __name__ == "__main__":
    table, notes = clean_production_mix_log()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
