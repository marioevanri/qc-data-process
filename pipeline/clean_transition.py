"""Clean the retail grade-change sheet: one row per sample taken while the RT line switches
from one grade to the next, until the new grade tastes right."""

import pandas as pd

from clean_production import production_or_none
from common import clean_analyst, clean_grade, drop_exact_duplicates, parse_date, production_day, read_source, squash

# samples of one change lie a few minutes apart, two changes on the line are hours apart
NEW_TRANSITION_GAP = pd.Timedelta(minutes=30)
# the first sample comes a minute or two after the new mix starts, never this long after
MIX_WINDOW = pd.Timedelta(minutes=30)
RESULTS = {"pass": "Pass", "ok": "Pass",
           "belumpass": "Belum Pass", "blmpass": "Belum Pass", "ng": "Belum Pass", "campur": "Belum Pass"}


def number_transitions(df, notes):
    """The sheet has no transition number. Samples of one change follow each other within
    minutes, so a gap of more than NEW_TRANSITION_GAP starts the next change."""
    df = df.sort_values("sample_time", kind="stable").reset_index(drop=True)
    new = df["sample_time"].diff() > NEW_TRANSITION_GAP
    new.iloc[0] = True
    df["transition_id"] = "TRN-" + new.cumsum().astype(str).str.zfill(4)
    df["sample_seq"] = df.groupby("transition_id").cumcount() + 1
    first = df.groupby("transition_id")["sample_time"].transform("min")
    df["minutes_after_first"] = ((df["sample_time"] - first).dt.total_seconds() / 60).round(1)
    # one change has one direction. A row written the other way round is a slip of the pen.
    for col in ["from_grade", "to_grade"]:
        usual = df.groupby("transition_id")[col].transform(lambda s: s.mode().iloc[0])
        notes[f"{col}_beda_dalam_transisi"] = int((df[col] != usual).sum())
        df[col] = usual
    notes["transisi"] = int(new.sum())
    return df


def find_mix(df, production, notes):
    """The mix being sampled is the first RT mix of the new grade: the last one that started
    before the first sample, at most MIX_WINDOW earlier. Without a production log the batch
    stays empty."""
    df["batch_no"], df["mix_letter"], df["minutes_after_mix_start"] = None, None, float("nan")
    if production is None:
        notes["transisi_tanpa_mix"] = df["transition_id"].nunique()
        return df
    rt = production[production["line"] == "RT"].sort_values("start")
    firsts = df.groupby("transition_id").agg(first=("sample_time", "min"), to_grade=("to_grade", "first"))
    found, wrong_grade = {}, 0
    for tid, row in firsts.iterrows():
        started = rt[(rt["start"] <= row["first"]) & (rt["start"] >= row["first"] - MIX_WINDOW)]
        if started.empty:
            continue
        mix = started.iloc[-1]
        wrong_grade += int(mix["grade"] != row["to_grade"])
        found[tid] = mix
    for col in ["batch_no", "mix_letter"]:
        df[col] = df["transition_id"].map({tid: m[col] for tid, m in found.items()})
    start = df["transition_id"].map({tid: m["start"] for tid, m in found.items()})
    df["minutes_after_mix_start"] = ((df["sample_time"] - start).dt.total_seconds() / 60).round(1)
    notes["transisi_tanpa_mix"] = df["transition_id"].nunique() - len(found)
    notes["mix_beda_grade"] = wrong_grade
    return df


def clean_retail_transition_samples(production=None):
    """production: the clean production log, or None to load it here (or to work without it)."""
    if production is None:
        production = production_or_none()
    df, notes = read_source("retail_transition_samples")
    df = drop_exact_duplicates(df, notes)

    # 1. when. The sheet has the calendar date, so a sample at 01:30 belongs to the
    #    production day before.
    df["sample_time"] = parse_date(df["sample_date"]) + pd.to_timedelta(df["sample_clock"].str.strip())
    df["prod_date"] = production_day(df["sample_time"]).dt.strftime("%Y-%m-%d")
    df["line"] = "RT"  # the sheet is only kept for the retail line

    # 2. what and who
    df["from_grade"] = clean_grade(df["from_grade"])
    df["to_grade"] = clean_grade(df["to_grade"])
    df["result"] = squash(df["result"]).map(RESULTS).fillna(df["result"].str.strip())
    notes["hasil_tidak_dikenal"] = int((~df["result"].isin(["Pass", "Belum Pass"])).sum())
    df["analyst_id"] = clean_analyst(df["analyst_id"])
    notes["analis_tidak_dikenal"] = int(df["analyst_id"].isna().sum())
    # only a sample that isn't right yet gets a note on what happened to it
    df["handling"] = df["handling"].str.strip().replace("", None)

    # 3. which change and which mix
    df = number_transitions(df, notes)
    df = find_mix(df, production, notes)

    df["sample_time"] = df["sample_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    notes["baris_bersih"] = len(df)
    columns = ["transition_id", "prod_date", "line", "from_grade", "to_grade", "batch_no", "mix_letter", "sample_seq",
               "sample_time", "minutes_after_first", "minutes_after_mix_start", "analyst_id", "result", "handling",
               "source_file"]
    return df[columns], notes


if __name__ == "__main__":
    table, notes = clean_retail_transition_samples()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
