"""Clean the micro lab results: one row per batch."""

import re

import numpy as np
import pandas as pd

from clean_production import production_or_none
from common import (clean_grade, date_from_batch, drop_exact_duplicates, parse_date, read_config, read_source,
                    repair_batch)


def load_limits():
    return {r["grade"]: r for r in read_config("batas_mikro.csv")}


def parse_count(text):
    """Plate count as written by the lab: '610' or '1,3 x 10^2'. Returns a number or NaN."""
    if not isinstance(text, str):
        return np.nan
    t = text.strip().replace(" ", "").lower()
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)x10\^(\d+)", t)
    if m:
        return float(m[1].replace(",", ".")) * 10 ** int(m[2])
    # '1.8E+0' is what Excel shows when the column is too narrow for '1.8E+03'. The exponent
    # is cut off, so 1.8E+0 can be 18, 180 or 1800. That can't be recovered from the sheet.
    if re.fullmatch(r"\d+(?:\.\d+)?e\+0", t):
        return np.nan
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return np.nan


def below_ten(series):
    """'<10' means below the detection limit: the count is unknown, only that it's under 10."""
    lt10 = series.str.strip() == "<10"
    count = pd.to_numeric(series.where(~lt10), errors="coerce")
    return count, lt10


def fail_reason(row, limits):
    """Same wording as the lab: 'coliform 20', 'TPC 7880, coliform 16', 'kapang/khamir 94'."""
    spec = limits.get(row["grade"])
    if spec is None:
        return None
    reasons = []
    if row["tpc_cfu_g"] > float(spec["tpc_maks"]):
        reasons.append(f"TPC {row['tpc_cfu_g']:.0f}")
    if not row["coliform_lt10"] and row["coliform_cfu_g"] >= float(spec["coliform_kurang_dari"]):
        reasons.append(f"coliform {row['coliform_cfu_g']:.0f}")
    if not row["ym_lt10"] and row["ym_cfu_g"] > float(spec["kapang_khamir_maks"]):
        reasons.append(f"kapang/khamir {row['ym_cfu_g']:.0f}")
    return ", ".join(reasons) or None


def clean_micro_results(production=None):
    """production: the clean production log, or None to load it here (or to work without it)."""
    if production is None:
        production = production_or_none()
    df, notes = read_source("micro_results")
    if production is None:
        notes["log_produksi"] = "tidak ada, batch tidak dicocokkan"

    # 1. the same row exported twice
    df = drop_exact_duplicates(df, notes)

    # 2. identity. The sheet has no production date, the sample reaches the lab the day after.
    df["grade"] = clean_grade(df["grade"])
    df["received_lab"] = parse_date(df["received_lab"])
    df["result_date"] = parse_date(df["result_date"])
    df["day_before"] = df["received_lab"] - pd.Timedelta(days=1)
    notes["batch_diperbaiki"], notes["batch_tidak_dikenal"] = repair_batch(df, production, date_col="day_before")
    df["line"] = df["batch_no"].str[-2:]
    df["prod_date"] = date_from_batch(df["batch_no"])

    # 3. counts
    df["tpc_cfu_g"] = df["tpc_raw"].map(parse_count)
    df["coliform_cfu_g"], df["coliform_lt10"] = below_ten(df["coliform_raw"])
    df["ym_cfu_g"], df["ym_lt10"] = below_ten(df["ym_raw"])
    notes["tpc_tidak_terbaca"] = int(df["tpc_cfu_g"].isna().sum())

    # 4. status as written by the lab, and the reason worked out from the spec
    df["micro_status"] = df["status_raw"].str.strip().str.upper().map({"MS": "Pass", "TMS": "Fail"})
    limits = load_limits()
    df["fail_reason"] = df.apply(fail_reason, axis=1, limits=limits)
    # the lab's status and the spec should agree. A mismatch means a typo in the count or the status.
    disagree = (df["micro_status"] == "Fail") != df["fail_reason"].notna()
    notes["status_tidak_cocok_dengan_spek"] = int(disagree.sum())

    for col in ["prod_date", "received_lab", "result_date"]:
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    notes["batch_ganda"] = int(df["batch_no"].duplicated().sum())
    columns = ["batch_no", "prod_date", "line", "grade", "received_lab", "result_date", "tpc_cfu_g",
               "coliform_cfu_g", "coliform_lt10", "ym_cfu_g", "ym_lt10", "ecoli", "salmonella",
               "micro_status", "fail_reason"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_micro_results()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
