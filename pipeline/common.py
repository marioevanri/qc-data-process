"""Small helpers shared by every cleaning script."""

import csv
import re
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR.parent / "generator" / "data" / "raw"
KEY_DIR = BASE_DIR.parent / "generator" / "data" / "clean"   # the generator's answer key
DB_PATH = BASE_DIR.parent / "db" / "qc.db"


def read_raw(path):
    """Read one raw export as text. Files saved from Excel with Indonesian settings use ; as separator."""
    header = pd.read_csv(path, nrows=0).columns
    sep = ";" if len(header) == 1 and ";" in header[0] else ","
    return pd.read_csv(path, dtype=str, sep=sep)


def load_grade_names():
    with open(BASE_DIR / "config" / "padanan_grade.csv", encoding="utf-8") as f:
        return {r["tulisan"]: r["grade"] for r in csv.DictReader(f)}


def clean_grade(series):
    """'NDC 28P', 'ndc-28p', 'NDC-28P ' all become NDC-28P. Unknown spellings stay as they are."""
    names = load_grade_names()
    key = series.str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    return key.map(names).fillna(series.str.strip())


def clean_batch(series):
    """'250102/61/RT' and '250102 61rt' become 25010261RT."""
    return series.str.upper().str.replace(r"[^0-9A-Z]", "", regex=True)


def clean_lot(series):
    """'po-250103-01', 'PO250108-01' and 'PO-250120-1' all become PO-250103-01 style."""
    def fix(value):
        m = re.fullmatch(r"([A-Z]+)-?(\d{6})-?(\d{1,2})", str(value).strip().upper())
        return f"{m[1]}-{m[2]}-{int(m[3]):02d}" if m else value
    return series.map(fix, na_action="ignore")


def to_number(series):
    """Text to number. Decimal commas are accepted, anything that isn't a number becomes empty."""
    return pd.to_numeric(series.str.strip().str.replace(",", ".", regex=False), errors="coerce")


def fix_decimal_shift(series, highest):
    """A value ten times too big is a slipped decimal point (1827.3 typed for 182.7)."""
    shifted = series > highest
    return series.where(~shifted, series / 10), int(shifted.sum())


def load_analysts():
    with open(BASE_DIR / "config" / "padanan_analis.csv", encoding="utf-8") as f:
        return {r["tulisan"]: r["analyst_id"] for r in csv.DictReader(f)}


def clean_analyst(series):
    """'Andi', 'ANDI', 'Andi P.', 'Andi Prasetyo' and 'AN01' all become AN01."""
    names = load_analysts()
    text = series.str.strip()
    first_word = text.str.lower().str.split().str[0]
    is_id = text.str.upper().str.fullmatch(r"AN\d{2}", na=False)
    return text.str.upper().where(is_id, first_word.map(names))


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


def fix_decimal_shift_by_group(values, groups, factor=4):
    """Slipped decimal point when the normal level differs per group (protein is 2 % in creamer, 20 % in milk).

    A value more than `factor` times the median of its own group is divided by 10.
    """
    median = values.groupby(groups).transform("median")
    shifted = values > factor * median
    return values.where(~shifted, values / 10), int(shifted.sum())
