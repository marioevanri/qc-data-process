"""Clean the KimFis lab sheets: one row per sample test, retests marked."""

import pandas as pd

from clean_production import clean_production_mix_log
from common import (RAW_DIR, after_shift_start, clean_analyst, clean_batch, clean_grade, clean_time,
                    fix_decimal_shift_by_group, read_raw, to_number)

# the sheet got new column names in January 2026, both spellings map to one name
RENAME = {
    "Tgl Produksi": "prod_date", "No Batch": "batch_no", "Grade": "grade", "Kode Sampel": "sample_code",
    "Jam Sampling": "sample_time", "Jam Uji": "test_time", "Analis": "analyst_id", "Ket": "notes",
    "KA (%)": "moisture_pct", "Lemak (%)": "fat_pct", "Protein (%)": "protein_pct",
    "Visko (cP)": "viscosity_cp", "Viskositas (cP)": "viscosity_cp", "Brix": "brix",
    "BD (g/ml)": "bulk_density", "Bulk Density": "bulk_density", "Kelarutan (ml)": "solubility_ml",
    "Wettability (s)": "wettability_s", "L*": "L_star", "pH": "ph", "Coffee Test": "coffee_test",
    "Retest (Y/N)": "retest_flag", "Line": "line_sheet",
}
NUMBERS = ["moisture_pct", "viscosity_cp", "brix", "fat_pct", "protein_pct", "bulk_density", "solubility_ml",
           "wettability_s", "L_star", "ph"]
COFFEE = {"pass": "Pass", "ok": "Pass", "tidak feathering": "Pass", "fail": "Fail", "feathering": "Fail"}


def read_all_sheets():
    sheets = []
    for path in sorted((RAW_DIR / "qc_lab").glob("KimFis_*.csv")):
        sheet = read_raw(path).rename(columns=RENAME)
        sheet["source_file"] = path.name
        sheets.append(sheet)
    return pd.concat(sheets, ignore_index=True)


def repair_batch(df, production):
    """Batch numbers typed by hand have typos. The production log knows which batch
    ran on a given date, grade and line, so a batch that doesn't exist is looked up there."""
    known = set(production["batch_no"])
    df["batch_no"] = clean_batch(df["batch_no"])
    wrong = ~df["batch_no"].isin(known)
    lookup = production.drop_duplicates(["prod_date", "grade", "line"]).set_index(["prod_date", "grade", "line"])["batch_no"]
    # the line is the last two characters of the batch, typos are almost always in the digits
    line = df["line_sheet"].str.strip().str.upper() if "line_sheet" in df else None
    line = df["batch_no"].str[-2:] if line is None else line.fillna(df["batch_no"].str[-2:])
    keys = pd.MultiIndex.from_arrays([df["prod_date"].dt.strftime("%Y-%m-%d"), df["grade"], line])
    rebuilt = pd.Series(lookup.reindex(keys).to_numpy(), index=df.index)
    fixable = wrong & rebuilt.notna()
    df.loc[fixable, "batch_no"] = rebuilt[fixable]
    return int(fixable.sum()), int((wrong & rebuilt.isna()).sum())


def clean_qc_lab_kimfis():
    production, _ = clean_production_mix_log()
    raw = read_all_sheets()
    notes = {"baris_raw": len(raw)}

    # 1. the same row exported twice
    df = raw.drop_duplicates(subset=[c for c in raw.columns if c != "source_file"]).copy()
    notes["duplikat_dibuang"] = len(raw) - len(df)

    # 2. identity columns
    df["prod_date"] = pd.to_datetime(df["prod_date"], format="%d/%m/%Y")
    df["grade"] = clean_grade(df["grade"])
    notes["batch_diperbaiki"], notes["batch_tidak_dikenal"] = repair_batch(df, production)
    df["line"] = df["batch_no"].str[-2:]
    # for samples taken after midnight some analysts write the calendar date instead of the
    # production date, so the production date is read from the batch number
    from_batch = pd.to_datetime(df["batch_no"].str[:6], format="%y%m%d", errors="coerce")
    notes["tanggal_bukan_tanggal_produksi"] = int((from_batch.notna() & (from_batch != df["prod_date"])).sum())
    df["prod_date"] = from_batch.fillna(df["prod_date"])
    # 'c1', 'B 2', 'B-2' and '2A' all mean one sample code
    code = df["sample_code"].str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    df["sample_code"] = code.str.replace(r"^(\d)([A-Z])$", r"\2\1", regex=True)
    df["sample_uid"] = df["batch_no"] + "-" + df["sample_code"]
    df["analyst_id"] = clean_analyst(df["analyst_id"])

    # 3. times. A sample can't be taken before its mix started, so when the clock time on the
    #    production date falls before the mix start, the sample was taken the next calendar day.
    #    This also catches the last sample of a night mix taken just after 07:00.
    mix_start = production.set_index("mix_id")["start"]
    started = pd.Series((df["batch_no"] + "-" + df["sample_code"].str[0]).map(mix_start).to_numpy(), index=df.index)
    clock = pd.to_timedelta(clean_time(df["sample_time"]) + ":00")
    df["sample_time"] = df["prod_date"] + clock
    df.loc[df["sample_time"] < started, "sample_time"] += pd.Timedelta(days=1)
    # no matching mix in the production log: fall back to the 07:00 rule
    no_mix = started.isna()
    df.loc[no_mix, "sample_time"] = after_shift_start(df.loc[no_mix, "prod_date"], clean_time(raw.loc[df.index[no_mix], "sample_time"]))
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

    df["prod_date"] = df["prod_date"].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    columns = ["sample_uid", "batch_no", "line", "grade", "prod_date", "sample_code", "sample_time", "test_time",
               "analyst_id"] + NUMBERS + ["coffee_test", "is_retest", "notes", "source_file"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_qc_lab_kimfis()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
