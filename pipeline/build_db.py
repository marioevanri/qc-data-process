"""Run every cleaning script and write the tables into one SQLite file.

Usage:
    python pipeline/build_db.py
"""

import sqlite3

from clean_lab import clean_qc_lab_kimfis
from clean_production import clean_production_mix_log
from common import DB_PATH

# table name in the database -> function that returns (clean table, notes)
TABLES = {
    "production_mix_log": clean_production_mix_log,
    "qc_lab_kimfis": clean_qc_lab_kimfis,
}


def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        for name, cleaner in TABLES.items():
            table, notes = cleaner()
            # SQLite has no date type, timestamps are stored as text it can still sort and compare
            for col in table.select_dtypes("datetime").columns:
                table[col] = table[col].dt.strftime("%Y-%m-%d %H:%M:%S")
            for col in table.select_dtypes("bool").columns:
                table[col] = table[col].astype(int)
            table.to_sql(name, con, if_exists="replace", index=False)
            print(f"{name}: {notes['baris_raw']} baris raw -> {len(table)} baris bersih")
    print(f"\nDatabase: {DB_PATH}")


if __name__ == "__main__":
    main()
