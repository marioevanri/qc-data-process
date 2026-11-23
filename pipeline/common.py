"""Helpers shared by every cleaning script.

Which files to read and which columns to take is not written here but in config/:
sumber_data.csv (sources), kolom.csv (column names), batas_wajar.csv (sensible ranges)
and the padanan_*.csv files (spellings).
"""

import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
RAW_DIR = BASE_DIR.parent / "generator" / "data" / "raw"
KEY_DIR = BASE_DIR.parent / "generator" / "data" / "clean"   # the generator's answer key
DOC_DIR = BASE_DIR.parent / "generator" / "docs"   # SOPs, specs and reports, also read by the assistant
DB_PATH = BASE_DIR.parent / "db" / "qc.db"

# date formats tried in this order. Day comes before month, as written in Indonesia.
DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]


class SourceOff(Exception):
    """The source is turned off in sumber_data.csv, or its files aren't there."""


# reading the config

def read_config(name):
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_padanan(name, key, value):
    """A spelling table from config/ as a dict, for example padanan_grade.csv: tulisan -> grade."""
    return {r[key]: r[value] for r in read_config(name)}


def column_config(table):
    return [r for r in read_config("kolom.csv") if r["tabel"] == table]


# reading raw files

def read_raw(path):
    """Read one raw export as text. Excel files are read directly. CSV files saved from Excel
    with Indonesian settings use ; as separator."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str)
    header = pd.read_csv(path, nrows=0).columns
    sep = ";" if len(header) == 1 and ";" in header[0] else ","
    return pd.read_csv(path, dtype=str, sep=sep)


def read_source(table):
    """All files of one source, with columns renamed to the standard names in kolom.csv.

    Columns not listed in kolom.csv are dropped. A listed column that isn't in the files is
    added empty, unless it is marked wajib, then reading stops with a clear message.
    Returns the table and a dict of notes.
    """
    sources = {r["tabel"]: r for r in read_config("sumber_data.csv")}
    src = sources.get(table)
    if src is None:
        raise SourceOff("tidak terdaftar di sumber_data.csv")
    if src["aktif"].strip().lower() != "ya":
        raise SourceOff("dimatikan di sumber_data.csv")
    files = sorted((RAW_DIR / src["folder"]).glob(src["pola_file"]))
    if not files:
        raise SourceOff(f"tidak ada file {src['folder']}/{src['pola_file']}")

    columns = column_config(table)
    rename = {r["kolom_raw"].strip(): r["kolom_baku"] for r in columns}
    sheets = []
    for path in files:
        sheet = read_raw(path)
        taken = {}
        for raw_name in sheet.columns:
            name = rename.get(str(raw_name).strip())
            if name is None:
                continue
            # two raw names for one standard column (a sheet that changed its headers): fill one from the other
            taken[name] = sheet[raw_name] if name not in taken else taken[name].fillna(sheet[raw_name])
        sheet = pd.DataFrame(taken, index=sheet.index)
        sheet["source_file"] = path.name
        sheets.append(sheet)
    df = pd.concat(sheets, ignore_index=True)

    wanted = list(dict.fromkeys(r["kolom_baku"] for r in columns))
    required = {r["kolom_baku"] for r in columns if r["wajib"].strip().lower() == "ya"}
    missing = [c for c in wanted if c not in df.columns]
    missing_required = [c for c in missing if c in required]
    if missing_required:
        raise ValueError(f"{table}: kolom wajib tidak ada di file: {', '.join(missing_required)}. "
                         "Cek nama kolom di config/kolom.csv.")
    for col in missing:
        df[col] = pd.Series(np.nan, index=df.index, dtype="object")
    notes = {"file": len(files), "baris_raw": len(df)}
    if missing:
        notes["kolom_tidak_ada"] = ", ".join(missing)
    return df, notes


def drop_exact_duplicates(df, notes):
    """The same row exported twice. The file name is ignored."""
    before = len(df)
    df = df.drop_duplicates(subset=[c for c in df.columns if c != "source_file"]).copy()
    notes["duplikat_dibuang"] = before - len(df)
    return df


# value cleaning

def parse_date(series):
    """Dates in any of DATE_FORMATS, plus Excel serial numbers (45649 is 23 December 2024)."""
    text = series.astype("object").where(series.notna(), None)
    text = pd.Series([str(v).strip() if v is not None else None for v in text], index=series.index, dtype="object")
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS:
        todo = result.isna() & text.notna()
        if not todo.any():
            break
        result[todo] = pd.to_datetime(text[todo], format=fmt, errors="coerce")
    serial = result.isna() & text.str.fullmatch(r"\d{5}", na=False)
    result[serial] = pd.Timestamp("1899-12-30") + pd.to_timedelta(text[serial].astype(int), unit="D")
    return result


def load_grade_names():
    return load_padanan("padanan_grade.csv", "tulisan", "grade")


def clean_grade(series):
    """'NDC 28P', 'ndc-28p', 'NDC-28P ' all become NDC-28P. Unknown spellings stay as they are."""
    names = load_grade_names()
    key = series.str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    return key.map(names).fillna(series.str.strip())


def clean_batch(series):
    """'250102/61/RT', '250102 61rt' and '25O10261RT' (letter O) become 25010261RT."""
    batch = series.str.upper().str.replace(r"[^0-9A-Z]", "", regex=True)
    # the first 8 characters are always digits, so O and I there are typos for 0 and 1
    digits = batch.str[:8].str.replace("O", "0", regex=False).str.replace("I", "1", regex=False)
    return digits + batch.str[8:]


def repair_batch(df, production, date_col="prod_date", date_must_match=False):
    """Batch numbers typed by hand have typos. The production log knows which batch
    ran on a given date, grade and line, so a batch that doesn't exist is looked up there.

    date_must_match: the date column is known to be the production date, so a batch whose
    date part differs from it is also a typo, even when that other batch exists
    (25101431P1 typed for 25011431P1).

    Without a production log only the spelling is cleaned. Changes df["batch_no"] in place
    and returns (repaired, still unknown).
    """
    df["batch_no"] = clean_batch(df["batch_no"])
    if production is None:
        return 0, 0
    known = set(production["batch_no"])
    wrong = ~df["batch_no"].isin(known)
    if date_must_match:
        wrong |= df["batch_no"].str[:6] != df[date_col].dt.strftime("%y%m%d")
    lookup = production.drop_duplicates(["prod_date", "grade", "line"]).set_index(["prod_date", "grade", "line"])["batch_no"]
    # the line is the last two characters of the batch, typos are almost always in the digits
    line = df["batch_no"].str[-2:]
    if "line_sheet" in df:
        line = df["line_sheet"].str.strip().str.upper().fillna(line)
    keys = pd.MultiIndex.from_arrays([df[date_col].dt.strftime("%Y-%m-%d"), df["grade"], line])
    rebuilt = pd.Series(lookup.reindex(keys).to_numpy(), index=df.index)
    fixable = wrong & rebuilt.notna()
    df.loc[fixable, "batch_no"] = rebuilt[fixable]
    return int(fixable.sum()), int((wrong & rebuilt.isna()).sum())


def typo_distance(a, b):
    """Number of typos between two strings of the same length. Two neighbours swapped
    (01 typed as 10) is one typo, not two."""
    count, i = 0, 0
    while i < len(a):
        if a[i] == b[i]:
            i += 1
            continue
        swapped = i + 1 < len(a) and a[i] == b[i + 1] and a[i + 1] == b[i]
        i += 2 if swapped else 1
        count += 1
    return count


def nearest_batch(df, production, date_col, days, notes):
    """For sheets with no production date to look a batch up by (a shipment, a release).
    A batch must have been made in the `days` before date_col. One that wasn't, or that isn't
    in the production log at all, is a typo: it's matched to the batch of the same grade made
    in that window with the fewest typos (typo_distance). On a tie the most recent batch is
    taken. A match more than 2 typos off is not taken, the batch stays as written and is
    counted in the notes.
    """
    df["batch_no"] = clean_batch(df["batch_no"])
    if production is None:
        return
    made = production.drop_duplicates("batch_no")[["batch_no", "grade", "prod_date"]].copy()
    made["prod_date"] = pd.to_datetime(made["prod_date"])
    made_on = df["batch_no"].map(made.set_index("batch_no")["prod_date"])
    in_window = (made_on <= df[date_col]) & (made_on >= df[date_col] - pd.Timedelta(days=days))
    suspect = df.index[~in_window & df["batch_no"].notna()]
    fixed = 0
    for i in suspect:
        typed, when = df.at[i, "batch_no"], df.at[i, date_col]
        pool = made[(made["grade"] == df.at[i, "grade"]) & (made["prod_date"] <= when)
                    & (made["prod_date"] >= when - pd.Timedelta(days=days))
                    & (made["batch_no"].str.len() == len(typed))]
        if pool.empty:
            continue
        distance = pool["batch_no"].map(lambda b: typo_distance(b, typed))
        if distance.min() > 2:
            continue
        best = pool[distance == distance.min()].sort_values("prod_date")
        df.at[i, "batch_no"] = best["batch_no"].iloc[-1]
        fixed += 1
    notes["batch_diperbaiki"] = fixed
    notes["batch_tidak_dikenal"] = len(suspect) - fixed


def date_from_batch(batch):
    """Production date written in the batch number: 25010231P1 is 2 January 2025."""
    return pd.to_datetime(batch.str[:6], format="%y%m%d", errors="coerce")


def mix_start_of(df, production):
    """Start time of the mix each sample came from, empty when there's no production log."""
    if production is None:
        return pd.Series(pd.NaT, index=df.index)
    start = pd.to_datetime(production.set_index("mix_id")["start"])
    mix_id = df["batch_no"] + "-" + df["sample_code"].str[0]
    return pd.Series(mix_id.map(start).to_numpy(), index=df.index)


def clean_sample_code(series):
    """'c1', 'B 2', 'B-2' and '2A' all mean one sample code."""
    code = series.str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    return code.str.replace(r"^(\d)([A-Z])$", r"\2\1", regex=True)


def clean_lot(series):
    """'po-250103-01', 'PO250108-01' and 'PO-250120-1' all become PO-250103-01 style."""
    def fix(value):
        m = re.fullmatch(r"([A-Z]+)-?(\d{6})-?(\d{1,2})", str(value).strip().upper())
        return f"{m[1]}-{m[2]}-{int(m[3]):02d}" if m else value
    return series.map(fix, na_action="ignore")


def to_number(series):
    """Text to number. Decimal commas are accepted, anything that isn't a number becomes empty."""
    return pd.to_numeric(series.astype("object").str.strip().str.replace(",", ".", regex=False), errors="coerce")


def apply_limits(df, table, notes):
    """Values outside the sensible range in batas_wajar.csv: divided by 10 (slipped decimal
    point) or emptied (sensor codes like 0 and 9999), as the file says."""
    for rule in read_config("batas_wajar.csv"):
        col = rule["kolom"]
        if rule["tabel"] != table or col not in df:
            continue
        low = float(rule["min"]) if rule["min"].strip() else -np.inf
        high = float(rule["maks"]) if rule["maks"].strip() else np.inf
        outside = (df[col] < low) | (df[col] > high)
        if rule["jika_di_luar"].strip() == "bagi 10":
            df.loc[df[col] > high, col] /= 10
        else:
            df.loc[outside, col] = np.nan
        notes[f"di_luar_batas_{col}"] = int(outside.sum())


def load_analysts():
    return load_padanan("padanan_analis.csv", "tulisan", "analyst_id")


def clean_analyst(series):
    """'Andi', 'ANDI', 'Andi P.', 'Andi Prasetyo' and 'AN01' all become AN01. Verifikator
    names work the same way: 'Hendra G.' becomes VR01."""
    names = load_analysts()
    text = series.str.strip()
    first_word = text.str.lower().str.split().str[0]
    is_id = text.str.upper().str.fullmatch(r"[A-Z]{2}\d{2}", na=False)
    return text.str.upper().where(is_id, first_word.map(names))


def squash(series):
    """Lowercase, no PT or CV, no spaces or punctuation, for matching names typed freely:
    'PT. Gula Pati Nusantara' -> 'gulapatinusantara', 'CV KKR' -> 'kkr'."""
    return (series.str.lower().str.replace(r"\b(pt|cv)\b", "", regex=True)
            .str.replace(r"[^a-z0-9]", "", regex=True))


def clean_time(series):
    """'10.31' becomes '10:31'."""
    return series.str.strip().str.replace(".", ":", regex=False)


def after_shift_start(prod_date, time_text):
    """Date and time of an event on a production day that runs 07:00 to 07:00.

    A sample taken at 02:00 on production date 3 January happened on 4 January.
    """
    time = pd.to_timedelta(time_text + ":00")
    next_day = pd.to_timedelta((time < pd.Timedelta(hours=7)).astype(int), unit="D")
    return prod_date + time + next_day


def production_day(timestamp):
    """The production date an event belongs to: before 07:00 counts as the previous day."""
    return (timestamp - pd.Timedelta(hours=7)).dt.normalize()


def fix_decimal_shift_by_group(values, groups, factor=4):
    """Slipped decimal point when the normal level differs per group (protein is 2 % in creamer, 20 % in milk).

    A value more than `factor` times the median of its own group is divided by 10.
    """
    median = values.groupby(groups).transform("median")
    shifted = values > factor * median
    return values.where(~shifted, values / 10), int(shifted.sum())


# product specs

def load_spec_limits():
    """Product specs, copied from RND's DCIS export into config/spek_produk.csv, with the table
    and column each parameter is measured in (config/padanan_parameter.csv). One row per grade,
    parameter and revision, so a sample can be judged by the revision valid on its production date."""
    spec = pd.DataFrame(read_config("spek_produk.csv"))
    where = pd.DataFrame(read_config("padanan_parameter.csv"))[["parameter", "tabel", "kolom"]]
    spec = spec.merge(where, on="parameter", how="left")
    for col in ["batas_min", "batas_maks"]:
        spec[col] = pd.to_numeric(spec[col].replace("", None))
    return spec.rename(columns={"kode_produk": "grade"})


# tables without a script of their own

def clean_generic(table):
    """Clean a table using only what kolom.csv says about each column (the tipe column):
    angka, tanggal, waktu, jam, grade, batch or teks. Enough for tidy sheets, like a
    formula list from RND, that need no special rules."""
    df, notes = read_source(table)
    df = drop_exact_duplicates(df, notes)
    for rule in column_config(table):
        col, kind = rule["kolom_baku"], rule["tipe"].strip()
        if kind == "angka":
            df[col] = to_number(df[col])
        elif kind == "tanggal":
            df[col] = parse_date(df[col]).dt.strftime("%Y-%m-%d")
        elif kind == "waktu":
            df[col] = parse_date(df[col])
        elif kind == "jam":
            df[col] = clean_time(df[col])
        elif kind == "grade":
            df[col] = clean_grade(df[col])
        elif kind == "batch":
            df[col] = clean_batch(df[col])
        else:
            df[col] = df[col].str.strip()
    apply_limits(df, table, notes)
    notes["baris_bersih"] = len(df)
    return df.reset_index(drop=True), notes
