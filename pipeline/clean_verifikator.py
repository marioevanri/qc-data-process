"""Clean the H+1 sensory re-check by the verifikator: one row per sample re-tasted."""

import pandas as pd

from clean_production import production_or_none
from clean_sensory import SCALE, SCORES, clean_result, off_flavor_type
from common import (clean_analyst, clean_grade, clean_sample_code, date_from_batch, drop_exact_duplicates, nearest_batch,
                    parse_date, read_source)


def clean_sensory_verifikator(production=None):
    """production: the clean production log, or None to load it here (or to work without it)."""
    if production is None:
        production = production_or_none()
    df, notes = read_source("sensory_verifikator")
    df = drop_exact_duplicates(df, notes)

    # 1. identity. The verifikator tastes 1 or 2 days after production, so a batch made
    #    outside that window is a typo and is matched like in shipments. The sheet only has
    #    the date of the test, not the time.
    df["test_date"] = parse_date(df["test_date"])
    df["grade"] = clean_grade(df["grade"])
    df["day_before"] = df["test_date"] - pd.Timedelta(days=1)
    nearest_batch(df, production, "day_before", days=1, notes=notes)
    df["prod_date"] = date_from_batch(df["batch_no"])
    df["sample_code"] = clean_sample_code(df["sample_code"])
    df["sample_uid"] = df["batch_no"] + "-" + df["sample_code"]
    df["verifikator_id"] = clean_analyst(df["verifikator_id"])
    notes["verifikator_tidak_dikenal"] = int(df["verifikator_id"].isna().sum())

    # 2. scores and results, same scale and spellings as the KimFis sensory sheet
    for col in SCORES:
        df[col] = df[col].str.lower().str.replace(" ", "", regex=False).map(SCALE)
    notes["skor_tidak_terbaca"] = int(df[SCORES].isna().sum().sum())
    df["grade_result"] = clean_result(df["grade_result"])
    df["off_flavor"] = df["grade_result"] == "TP3"
    df["off_flavor_type"] = df["notes"].map(off_flavor_type).where(df["off_flavor"])
    # what KimFis gave the same sample, as copied by the verifikator. Often left empty, the
    # queries take the KimFis result from sensory_kimfis instead.
    df["kimfis_grade"] = clean_result(df["kimfis_grade"])

    for col in ["test_date", "prod_date"]:
        df[col] = df[col].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    notes["sample_uid_ganda"] = int(df["sample_uid"].duplicated().sum())
    columns = ["sample_uid", "batch_no", "grade", "prod_date", "sample_code", "test_date", "verifikator_id"] + SCORES + [
        "off_flavor", "off_flavor_type", "grade_result", "kimfis_grade", "notes", "source_file"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_sensory_verifikator()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
