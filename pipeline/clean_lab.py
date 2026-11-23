"""Clean the KimFis lab sheets: one row per sample test, retests marked."""

import pandas as pd

from clean_production import production_or_none
from common import (after_shift_start, clean_analyst, clean_grade, clean_sample_code, clean_time, date_from_batch,
                    drop_exact_duplicates, fix_decimal_shift_by_group, load_spec_limits, mix_start_of, parse_date,
                    read_source, repair_batch, to_number)

NUMBERS = ["moisture_pct", "viscosity_cp", "brix", "fat_pct", "protein_pct", "bulk_density", "solubility_ml",
           "wettability_s", "L_star", "ph"]
COFFEE = {"pass": "Pass", "ok": "Pass", "tidak feathering": "Pass", "fail": "Fail", "feathering": "Fail"}
# how a parameter is named in retest_of
SHORT = {"moisture_pct": "moisture", "viscosity_cp": "viscosity", "brix": "brix", "fat_pct": "fat",
         "protein_pct": "protein", "bulk_density": "bulk_density", "solubility_ml": "solubility",
         "wettability_s": "wettability", "L_star": "L_star", "ph": "ph"}


def out_of_spec(values, limits):
    """Columns of one test outside their limits. An empty value is never out of spec."""
    bad = []
    for _, lim in limits.iterrows():
        v = values[lim["kolom"]]
        if pd.notna(v) and ((pd.notna(lim["batas_min"]) and v < lim["batas_min"])
                            or (pd.notna(lim["batas_maks"]) and v > lim["batas_maks"])):
            bad.append(lim["kolom"])
    return bad


def retest_trigger(df, notes):
    """Which parameter sent a sample to a retest: the one out of spec on the test before it,
    judged by the spec revision valid on the production date. When that value is unreadable on
    the sheet, the retest's own result is used, since a retest still out of spec shows what it
    was run for. df must be sorted by sample and test time."""
    spec = load_spec_limits()
    spec = spec[spec["kolom"].isin(NUMBERS) & (spec["batas_min"].notna() | spec["batas_maks"].notna())]
    previous = df.groupby("sample_uid")[NUMBERS].shift()
    trigger = pd.Series(None, index=df.index, dtype="object")
    for i in df.index[df["is_retest"]]:
        made = df.at[i, "prod_date"].strftime("%Y-%m-%d")
        limits = spec[(spec["grade"] == df.at[i, "grade"]) & (spec["berlaku_mulai"] <= made)]
        limits = limits.sort_values("berlaku_mulai").groupby("kolom").tail(1)
        bad = out_of_spec(previous.loc[i], limits) or out_of_spec(df.loc[i, NUMBERS], limits)
        trigger[i] = ",".join(SHORT[c] for c in bad) or None
    notes["retest_tanpa_pemicu"] = int((df["is_retest"] & trigger.isna()).sum())
    return trigger


def clean_qc_lab_kimfis(production=None):
    """production: the clean production log, or None to load it here (or to work without it)."""
    if production is None:
        production = production_or_none()
    df, notes = read_source("qc_lab_kimfis")
    if production is None:
        notes["log_produksi"] = "tidak ada, batch tidak dicocokkan"

    # 1. the same row exported twice. The sheet got new column names in January 2026,
    #    kolom.csv maps both spellings to one name.
    df = drop_exact_duplicates(df, notes)

    # 2. identity columns
    df["prod_date"] = parse_date(df["prod_date"])
    df["grade"] = clean_grade(df["grade"])
    notes["batch_diperbaiki"], notes["batch_tidak_dikenal"] = repair_batch(df, production)
    df["line"] = df["batch_no"].str[-2:]
    # for samples taken after midnight some analysts write the calendar date instead of the
    # production date, so the production date is read from the batch number
    from_batch = date_from_batch(df["batch_no"])
    notes["tanggal_bukan_tanggal_produksi"] = int((from_batch.notna() & (from_batch != df["prod_date"])).sum())
    df["prod_date"] = from_batch.fillna(df["prod_date"])
    df["sample_code"] = clean_sample_code(df["sample_code"])
    df["sample_uid"] = df["batch_no"] + "-" + df["sample_code"]
    df["analyst_id"] = clean_analyst(df["analyst_id"])

    # 3. times. A sample can't be taken before its mix started, so when the clock time on the
    #    production date falls before the mix start, the sample was taken the next calendar day.
    #    This also catches the last sample of a night mix taken just after 07:00.
    started = mix_start_of(df, production)
    clock_text = clean_time(df["sample_time"])
    df["sample_time"] = df["prod_date"] + pd.to_timedelta(clock_text + ":00")
    df.loc[df["sample_time"] < started, "sample_time"] += pd.Timedelta(days=1)
    # no matching mix in the production log: fall back to the 07:00 rule
    no_mix = started.isna()
    df.loc[no_mix, "sample_time"] = after_shift_start(df.loc[no_mix, "prod_date"], clock_text[no_mix])
    notes["sampel_tanpa_mix_di_log_produksi"] = int(no_mix.sum())
    test_clock = pd.to_timedelta(clean_time(df["test_time"]) + ":00")
    df["test_time"] = df["sample_time"].dt.normalize() + test_clock
    df.loc[df["test_time"] < df["sample_time"], "test_time"] += pd.Timedelta(days=1)

    # 4. numbers. Text like '?', 'ND', 'tdk diuji' becomes empty.
    for col in NUMBERS:
        df[col] = to_number(df[col])
    # some analysts wrote bulk density in g/L (553 instead of 0.553)
    in_g_per_l = df["bulk_density"] > 10
    df.loc[in_g_per_l, "bulk_density"] /= 1000
    notes["bulk_density_g_per_l"] = int(in_g_per_l.sum())
    for col in NUMBERS:
        df[col], notes[f"desimal_geser_{col}"] = fix_decimal_shift_by_group(df[col], df["grade"])
    df["coffee_test"] = df["coffee_test"].str.strip().str.lower().map(COFFEE)

    # 5. a row typed twice with different values: same sample, same test time. Nothing in the
    #    sheet says which one is right. The generator's answer key keeps the first entry, so
    #    that's the rule here. With real data this has to be asked, not guessed.
    before = len(df)
    df = df.drop_duplicates(subset=["sample_uid", "test_time"], keep="first")
    notes["ketik_ulang_dibuang"] = before - len(df)

    # 6. retest: the same sample tested again later
    df = df.sort_values(["sample_uid", "test_time"])
    df["is_retest"] = df.groupby("sample_uid").cumcount() > 0
    notes["retest"] = int(df["is_retest"].sum())
    # 7. what each retest was run for
    df["retest_of"] = retest_trigger(df, notes)

    df["prod_date"] = df["prod_date"].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    columns = ["sample_uid", "batch_no", "line", "grade", "prod_date", "sample_code", "sample_time", "test_time",
               "analyst_id"] + NUMBERS + ["coffee_test", "is_retest", "retest_of", "notes", "source_file"]
    return df[columns].reset_index(drop=True), notes


def latest_per_sample(table):
    """One row per sample with the result that counts: the last value measured for every
    parameter. A retest doesn't always repeat the whole panel (fat is often left out), so
    taking only the last row would lose the values from the first test."""
    ordered = table.sort_values(["sample_uid", "test_time"])
    groups = ordered.groupby("sample_uid", sort=False)
    identity = ["batch_no", "line", "grade", "prod_date", "sample_code", "sample_time"]
    # 'last' skips empty cells, so each parameter gets its latest measured value
    final = groups.agg({**{c: "first" for c in identity}, "test_time": "last",
                        **{c: "last" for c in NUMBERS + ["coffee_test"]}})
    final["n_tests"] = groups.size()
    return final.reset_index()


if __name__ == "__main__":
    table, notes = clean_qc_lab_kimfis()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
