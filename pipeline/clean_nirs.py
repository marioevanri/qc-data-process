"""Clean the NIRS export: one row per scan, linked to its sample or control."""

import re

import numpy as np
import pandas as pd

from clean_production import production_or_none
from common import (SourceOff, clean_generic, clean_grade, date_from_batch, drop_exact_duplicates, parse_date,
                    production_day, read_source, to_number)

LINES = "P1|P2|RT"
BATCH = re.compile(rf"(\d{{8}}(?:{LINES}))")
SHORT = re.compile(rf"^([A-Z]\d{{1,2}})\s+(\d{{2}}(?:{LINES}))$")   # 'A2 31P1': no date in the name
CONTROL_ID = re.compile(r"CTRL-\d{2}-\d{3}")


def split_name(name):
    """Sample name typed in the NIRS software, in any of the ways analysts write it:
    '25010247P2 A1', 'A1-25010231P1', '25010231P1B3', 'A2 31P1', and for controls 'CTRL-31-001',
    'CTRL CRM-RT', 'Kontrol FMP-26 0201' or 'kontrol 61'. Anything else ('test', 'trial RND') is unknown.
    Returns (kind, batch_or_grade_line_or_control_id, sample_code)."""
    text = str(name).strip().upper()
    m = CONTROL_ID.fullmatch(text)
    if m:
        return "control_id", text, None
    if text.startswith(("CTRL", "KONTROL")):
        return "control", None, None
    m = SHORT.match(text)
    if m:
        return "short", m[2], m[1]
    m = BATCH.search(text)
    if m:
        code = re.sub(r"[^A-Z0-9]", "", text.replace(m[1], ""))
        return "sample", m[1], code
    return "unknown", None, None


def pick_batch(scan_time, grade_line, sample_code, starts):
    """For a name without a date: the batch is from the production day of the scan or the
    day before (a night sample scanned after 07:00). The first letter of the sample code is
    the mix, so look at when that mix started on each day and take the latest one that had
    already started when the scan was made."""
    day = production_day(pd.Series([scan_time]))[0]
    candidates = [f"{d:%y%m%d}{grade_line}" for d in (day, day - pd.Timedelta(days=1))]
    if starts is None:
        return candidates[0]
    best, best_start = None, None
    for batch in candidates:
        start = starts.get((batch, sample_code[0]))
        if start is not None and start <= scan_time and (best_start is None or start > best_start):
            best, best_start = batch, start
    return best or candidates[0]


def control_from_log(grade, day, log):
    if log is None:
        return None
    in_use = (log["grade"] == grade) & (log["start"] <= day) & (day < log["end"])
    return log.loc[in_use, "control_id"].iloc[0] if in_use.any() else None


def controls_dated(df, control, notes):
    """A control scan has no batch. It is scanned just before the first sample of a run (one
    grade on one line on one production day), sometimes after midnight for a night run, so it
    takes the date and line of the next run that starts. When a grade runs on two lines the
    same day and both controls are scanned before either run starts, the name doesn't say
    which control went with which line. Those get the date but the line stays empty."""
    samples = df.loc[~control & df["prod_date"].notna()].sort_values("scan_time")
    runs = (samples.groupby(["grade", "line", "prod_date"], as_index=False)["scan_time"].first()
            .rename(columns={"scan_time": "first_scan", "line": "run_line", "prod_date": "run_date"})
            .sort_values("first_scan"))
    ctrl = df.loc[control, ["scan_time", "grade"]].reset_index().sort_values("scan_time")
    ctrl = pd.merge_asof(ctrl, runs[["grade", "run_date", "first_scan"]], left_on="scan_time",
                         right_on="first_scan", by="grade", direction="forward")
    # first control of the day goes with the first run, the second with the second
    ctrl["n"] = ctrl.groupby(["grade", "run_date"], dropna=False).cumcount()
    runs["n"] = runs.groupby(["grade", "run_date"]).cumcount()
    ctrl = ctrl.merge(runs[["grade", "run_date", "n", "run_line"]], on=["grade", "run_date", "n"], how="left")
    group = ctrl.groupby(["grade", "run_date"], dropna=False)
    unclear = (group["index"].transform("size") > 1) & (group["scan_time"].transform("max") < group["first_scan"].transform("min"))
    ctrl.loc[unclear, "run_line"] = None
    notes["kontrol_line_tidak_jelas"] = int(unclear.sum())

    # a control after the last run in the file: fall back to the production day of the scan
    df.loc[ctrl["index"], "prod_date"] = ctrl["run_date"].fillna(production_day(ctrl["scan_time"])).to_numpy()
    df.loc[ctrl["index"], "line"] = ctrl["run_line"].to_numpy()


def clean_nirs_results(production=None):
    """production: the clean production log, or None to load it here (or to work without it).
    Every scan is kept. scan_type says what was scanned: sample, control or other, and
    is_latest marks the scan to use when a sample was scanned more than once."""
    if production is None:
        production = production_or_none()
    df, notes = read_source("nirs_results")
    df = drop_exact_duplicates(df, notes)
    df["scan_time"] = parse_date(df["scan_time"])

    # 1. a scan repeated right away gets an R behind its number, like a retest in the lab.
    #    It's kept and marked. The rescan is the same sample, so it gets its identity from
    #    the first scan further down, and only first scans go through steps 3 to 5.
    rescan = df["scan_id"].str.endswith("R") & df["scan_id"].str[:-1].isin(df["scan_id"])
    df["is_rescan"] = rescan
    df["rescan_of"] = df["scan_id"].str[:-1].where(rescan)
    notes["scan_ulang"] = int(rescan.sum())
    again, df = df[rescan].copy(), df[~rescan].copy()

    # 2. the prediction model, NDC28P_v2, also says the grade
    df["grade"] = clean_grade(df["product_model"].str.replace(r"_v\d+$", "", regex=True))

    # 3. what the sample name says. Scans that aren't production samples or controls are kept
    #    as 'other': instrument checks ('test', 'xx', 'cek alat'), competitor samples and RND
    #    trials. They get no grade, the model used to scan them says nothing about the sample.
    parts = df["sample_name"].map(split_name)
    kind = parts.str[0]
    df["scan_type"] = kind.map({"sample": "sample", "short": "sample", "control": "control",
                                "control_id": "control"}).fillna("other")
    notes["scan_lain"] = int((df["scan_type"] == "other").sum())
    df.loc[df["scan_type"] == "other", "grade"] = None
    df["sample_code"] = parts.str[2]
    df["batch_no"] = np.where(kind == "sample", parts.str[1], None)
    # start of every mix, for names without a date
    starts = None
    if production is not None:
        starts = dict(zip(zip(production["batch_no"], production["mix_letter"]), pd.to_datetime(production["start"])))
    short = kind == "short"
    df.loc[short, "batch_no"] = [pick_batch(t, gl, code, starts) for t, gl, code in
                                 zip(df.loc[short, "scan_time"], parts[short].str[1], parts[short].str[2])]
    notes["nama_tanpa_tanggal"] = int(short.sum())

    # 4. controls: written as an ID, or as 'Kontrol <grade> <ddmm>' that has to be looked up
    df["is_control"] = df["scan_type"] == "control"
    df["control_id"] = np.where(kind == "control_id", parts.str[1], None)
    try:
        log, _ = clean_generic("sensory_controls")
        log["start"] = pd.to_datetime(log["start_use"])
        log["end"] = pd.to_datetime(log["end_use"]).fillna(pd.Timestamp.max)
    except SourceOff:
        log = None
    # 5. a sample's production date and line are in its batch, a control takes them from
    #    the run it was scanned for
    control = df["is_control"]
    df["prod_date"] = date_from_batch(df["batch_no"])
    df["line"] = df["batch_no"].str[-2:]
    controls_dated(df, control, notes)
    by_name = kind == "control"
    df.loc[by_name, "control_id"] = [control_from_log(g, d, log) for g, d in
                                    zip(df.loc[by_name, "grade"], df.loc[by_name, "prod_date"])]
    df["sample_uid"] = (df["batch_no"] + "-" + df["sample_code"]).where(df["scan_type"] == "sample")

    # 6. rescans copy everything about the sample from their first scan
    identity = ["grade", "scan_type", "is_control", "control_id", "prod_date", "line", "sample_uid"]
    first = df.set_index("scan_id")[identity]
    again = again.join(first, on="rescan_of")
    df = pd.concat([df, again]).sort_values(["scan_time", "scan_id"], kind="stable")
    # all scans are kept, the one that counts is the last scan of a sample. A control or
    # other scan only has its own rescan.
    sample = df["sample_uid"].where(df["scan_type"] == "sample")
    chain = sample.fillna(df["rescan_of"].fillna(df["scan_id"]))
    df["is_latest"] = ~chain.duplicated(keep="last")

    for col in ["pred_moisture", "pred_fat", "pred_protein"]:
        df[col] = to_number(df[col])

    df["prod_date"] = df["prod_date"].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    columns = ["scan_id", "scan_time", "scan_type", "line", "grade", "prod_date", "is_control", "control_id",
               "sample_uid", "is_rescan", "rescan_of", "is_latest", "pred_moisture", "pred_fat", "pred_protein",
               "product_model", "instrument", "sample_name", "source_file"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_nirs_results()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
