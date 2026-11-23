"""Clean the KimFis sensory sheets: one row per tasted sample."""

from difflib import SequenceMatcher

import pandas as pd

from clean_production import production_or_none
from common import (SourceOff, after_shift_start, clean_analyst, clean_generic, clean_grade, clean_sample_code,
                    clean_time, date_from_batch, drop_exact_duplicates, mix_start_of, parse_date, read_source,
                    repair_batch)

# SOP-QC-005 Rev 03 changed the sheet in January 2026: scores became numbers, a control ID
# column was added, and "Hasil" became "Grade Sensory". kolom.csv keeps the two result
# columns apart (result_old, result_new) because one file has both.
SCORES = ["score_creamy", "score_mouthfeel", "score_milky", "score_sweetness"]

# every way the scale was written, Rev 02 words and Rev 03 numbers, after lowercasing and removing spaces
SCALE = {
    "pass": 0, "0": 0, "sesuai": 0, "ok": 0,
    "agaklebih": 1, "agklebih": 1, "al": 1, "1": 1, "+1": 1, "1+": 1,
    "agakkurang": -1, "agkkurang": -1, "ak": -1, "-1": -1, "1-": -1, "kurangdikit": -1,
    "lebih": 2, "2": 2, "+2": 2, "2+": 2,
    "kurang": -2, "-2": -2, "2-": -2,
}
# first letters of the attribute as it shows up in the notes, typos included ("crreamy", "moutheel")
NOTE_ATTRIBUTE = {"cr": "score_creamy", "mo": "score_mouthfeel", "mi": "score_milky", "ma": "score_sweetness"}

# kind of off-flavor, from keywords in the notes
OFF_FLAVOR = [
    ("oxid", ["tengik", "oily", "oksid"]),
    ("mixgrade", ["grade", "campur", "kebawa", "transisi"]),
    ("burnt", ["gosong", "burnt", "sangit"]),
]


def clean_result(series):
    """'PASS', 'P', 'TP1 +', 'TP1(+)', 'TP 1+' and 'tp3' to Pass, TP1+, TP1-, TP2+, TP2-, TP3."""
    text = series.str.upper().str.replace(r"[^A-Z0-9+-]", "", regex=True)
    return text.replace({"PASS": "Pass", "P": "Pass"})


def scores_from_notes(note):
    """'creamy agak lebih, mouthfeel agak kurang' -> {'score_creamy': 1, 'score_mouthfeel': -1}."""
    found = {}
    for part in str(note).lower().split(","):
        part = part.strip()
        column = NOTE_ATTRIBUTE.get(part[:2])
        if column and "leb" in part:
            found[column] = 1
        elif column and "kur" in part:
            found[column] = -1
    return found


def similar(word, keyword):
    """Typos like 'tenggik', 'tegik' and 'tengk' still count as 'tengik', and so does a word
    typed without its space ('aromatengik')."""
    return keyword in word or SequenceMatcher(None, word, keyword).ratio() >= 0.75


def off_flavor_type(note):
    words = str(note).lower().replace(",", " ").replace("/", " ").split()
    for kind, keywords in OFF_FLAVOR:
        if any(similar(w, k) for w in words for k in keywords):
            return kind
    return "random"  # apek, kurang fresh, aroma asing


def control_lookup(df):
    """Control in use for that grade on the production date, from the control log (the
    sensory_controls table). Needed for 2025, when the sheet had no control column, and for
    empty cells in 2026. A night sample tasted after midnight still belongs to the production
    day it was made. Without the control log the IDs stay as written on the sheet."""
    found = pd.Series(pd.NA, index=df.index, dtype="object")
    try:
        log, _ = clean_generic("sensory_controls")
    except SourceOff:
        return found
    start = pd.to_datetime(log["start_use"])
    # the last control has no replacement date yet
    end = pd.to_datetime(log["end_use"]).fillna(pd.Timestamp.max)
    day = pd.to_datetime(df["prod_date"])
    for i in log.index:
        in_use = (df["grade"] == log.at[i, "grade"]) & (day >= start[i]) & (day < end[i])
        found[in_use & found.isna()] = log.at[i, "control_id"]
    return found


def clean_sensory_kimfis(production=None):
    """production: the clean production log, or None to load it here (or to work without it)."""
    if production is None:
        production = production_or_none()
    df, notes = read_source("sensory_kimfis")
    if production is None:
        notes["log_produksi"] = "tidak ada, batch tidak dicocokkan"

    # 1. the same row exported twice
    df = drop_exact_duplicates(df, notes)

    # 2. identity columns, same rules as the lab sheet
    df["prod_date"] = parse_date(df["prod_date"])
    df["grade"] = clean_grade(df["grade"])
    # the date on the sensory sheet is always the production date
    notes["batch_diperbaiki"], notes["batch_tidak_dikenal"] = repair_batch(df, production, date_must_match=True)
    df["line"] = df["batch_no"].str[-2:]
    df["prod_date"] = date_from_batch(df["batch_no"]).fillna(df["prod_date"])
    df["sample_code"] = clean_sample_code(df["sample_code"])
    df["sample_uid"] = df["batch_no"] + "-" + df["sample_code"]
    df["analyst_id"] = clean_analyst(df["analyst_id"])

    # 3. test time. A sample can't be tasted before its mix started.
    started = mix_start_of(df, production)
    clock = clean_time(df["test_time"])
    df["test_time"] = df["prod_date"] + pd.to_timedelta(clock + ":00")
    df.loc[df["test_time"] < started, "test_time"] += pd.Timedelta(days=1)
    no_mix = started.isna()
    df.loc[no_mix, "test_time"] = after_shift_start(df.loc[no_mix, "prod_date"], clock[no_mix])

    # 4. scores. Words and numbers on one scale, -2 to +2.
    for col in SCORES:
        df[col] = df[col].str.lower().str.replace(" ", "", regex=False).map(SCALE)
    # an empty score is filled from the notes, where the analyst names every attribute that deviates.
    # Not named there means it matched the control.
    missing = df[SCORES].isna().any(axis=1)
    notes["skor_kosong_diisi_dari_catatan"] = int(df[SCORES].isna().sum().sum())
    for i in df.index[missing]:
        from_note = scores_from_notes(df.at[i, "notes"])
        for col in SCORES:
            if pd.isna(df.at[i, col]):
                df.at[i, col] = from_note.get(col, 0)
    df[SCORES] = df[SCORES].astype(int)

    # 5. result and off-flavor
    df["grade_result"] = clean_result(df["result_new"].fillna(df["result_old"]))
    df["off_flavor"] = df["grade_result"] == "TP3"
    df["off_flavor_type"] = df["notes"].map(off_flavor_type).where(df["off_flavor"])
    # the result follows from the scores (SOP-QC-005 section 7). A mismatch is worth a look.
    worst = df[SCORES].abs().max(axis=1)
    expected = worst.map({0: "Pass", 1: "TP1", 2: "TP2"})
    agrees = df["off_flavor"] | (df["grade_result"].str[:3] == expected.str[:3])
    notes["hasil_tidak_cocok_dengan_skor"] = int((~agrees).sum())

    # 6. control sample
    df["control_id"] = df["control_id"].str.strip().str.upper()
    from_log = control_lookup(df)
    notes["kontrol_dari_log"] = int(df["control_id"].isna().sum())
    df["control_id"] = df["control_id"].fillna(from_log)

    df["prod_date"] = df["prod_date"].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    notes["sample_uid_ganda"] = int(df["sample_uid"].duplicated().sum())
    columns = ["sample_uid", "batch_no", "line", "grade", "prod_date", "sample_code", "test_time", "analyst_id",
               "control_id"] + SCORES + ["off_flavor", "off_flavor_type", "grade_result", "notes", "source_file"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_sensory_kimfis()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
