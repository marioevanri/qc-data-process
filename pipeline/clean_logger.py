"""Clean the spray dryer logger: one reading every 30 minutes per line."""

import re

import numpy as np

from common import apply_limits, drop_exact_duplicates, parse_date, read_config, read_source, to_number

SENSORS = ["inlet_temp", "outlet_temp", "homog_p1_bar", "homog_p2_bar", "emulsion_temp", "ambient_rh"]


def blank_stuck(df, notes):
    """A sensor that hangs keeps sending its last value. The same value more times in a row
    than maks_sama_berturut in batas_wajar.csv is emptied, the real value is unknown.
    df has to be sorted by line and time."""
    for rule in read_config("batas_wajar.csv"):
        col, limit = rule["kolom"], (rule.get("maks_sama_berturut") or "").strip()
        if rule["tabel"] != "dryer_logger" or not limit or col not in df:
            continue
        value = df[col]
        run = ((value != value.shift()) | (df["line"] != df["line"].shift())).cumsum()
        stuck = value.notna() & (value.groupby(run).transform("size") > int(limit))
        df.loc[stuck, col] = np.nan
        notes[f"sensor_macet_{col}"] = int(stuck.sum())


def clean_dryer_logger(production=None):
    """production is not used, the argument is there so every cleaner is called the same way."""
    df, notes = read_source("dryer_logger")
    df = drop_exact_duplicates(df, notes)

    # the line is only in the file name: Dryer_P1_2025-01.csv
    df["line"] = df["source_file"].map(lambda f: (re.search(r"_(P1|P2|RT)_", f) or [None, None])[1])
    df["timestamp"] = parse_date(df["timestamp"])
    for col in SENSORS:
        df[col] = to_number(df[col])
    # 0 and 9999 are what the logger writes when a sensor drops out, ranges are in batas_wajar.csv
    apply_limits(df, "dryer_logger", notes)

    # the logger sometimes writes two readings with the same time stamp, mostly at 07:00 and
    # 07:30 when the shift changes. Both are kept, following the answer key. With a real
    # logger, ask the supplier which reading is the right one before averaging or dropping.
    notes["waktu_ganda"] = int(df.duplicated(["timestamp", "line"]).sum())
    df = df.sort_values(["line", "timestamp"], kind="stable").reset_index(drop=True)
    blank_stuck(df, notes)
    notes["baris_bersih"] = len(df)
    return df[["timestamp", "line"] + SENSORS], notes


if __name__ == "__main__":
    table, notes = clean_dryer_logger()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
