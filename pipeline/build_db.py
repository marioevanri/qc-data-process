"""Run every cleaning script and write the tables into one SQLite file.

Which tables are built is decided by config/sumber_data.csv. A table that is turned off
there, or whose files aren't found, is skipped and removed from the database. A table
without its own script is cleaned with clean_generic, using only config/kolom.csv.

Usage:
    python pipeline/build_db.py
"""

import sqlite3

from clean_complaints import clean_complaints
from clean_controls import clean_sensory_controls
from clean_lab import clean_qc_lab_kimfis, latest_per_sample
from clean_logger import clean_dryer_logger
from clean_micro import clean_micro_results
from clean_nirs import clean_nirs_results
from clean_production import clean_production_mix_log
from clean_release import clean_release_history
from clean_rm import clean_rm_receiving
from clean_sensory import clean_sensory_kimfis
from clean_shipments import clean_shipments
from clean_transition import clean_retail_transition_samples
from clean_verifikator import clean_sensory_verifikator
from common import DB_PATH, SourceOff, clean_generic, load_spec_limits, read_config

# tables with special rules. Each takes the clean production log (or None) and returns (table, notes).
CLEANERS = {
    "qc_lab_kimfis": clean_qc_lab_kimfis,
    "sensory_kimfis": clean_sensory_kimfis,
    "sensory_controls": clean_sensory_controls,
    "micro_results": clean_micro_results,
    "nirs_results": clean_nirs_results,
    "rm_receiving": clean_rm_receiving,
    "dryer_logger": clean_dryer_logger,
    "sensory_verifikator": clean_sensory_verifikator,
    "release_history": clean_release_history,
    "shipments": clean_shipments,
    "complaints": clean_complaints,
    "retail_transition_samples": clean_retail_transition_samples,
}

# tables made from a clean table and saved next to it: one row per sample, latest result
DERIVED = {
    "qc_lab_kimfis": ("qc_lab_final", latest_per_sample),
}


def save(con, name, table):
    # SQLite has no date or boolean type: timestamps become sortable text, True/False become 1/0
    for col in table.select_dtypes("datetime").columns:
        table[col] = table[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    for col in table.select_dtypes("bool").columns:
        table[col] = table[col].astype(int)
    table.to_sql(name, con, if_exists="replace", index=False)


def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    names = [r["tabel"] for r in read_config("sumber_data.csv")]
    with sqlite3.connect(DB_PATH) as con:
        # the production log goes first because the other tables use it to repair batch numbers
        production = None
        try:
            production, notes = clean_production_mix_log()
            save(con, "production_mix_log", production.copy())
            print(f"production_mix_log: {notes['baris_raw']} baris raw -> {len(production)} baris bersih")
        except SourceOff as e:
            con.execute("DROP TABLE IF EXISTS production_mix_log")
            print(f"production_mix_log: dilewati, {e}. Tabel lain jalan tanpa perbaikan batch.")

        for name in names:
            if name == "production_mix_log":
                continue
            try:
                if name in CLEANERS:
                    table, notes = CLEANERS[name](production)
                else:
                    table, notes = clean_generic(name)
            except SourceOff as e:
                con.execute(f"DROP TABLE IF EXISTS {name}")
                if name in DERIVED:
                    con.execute(f"DROP TABLE IF EXISTS {DERIVED[name][0]}")
                print(f"{name}: dilewati, {e}")
                continue
            if name in DERIVED:
                derived_name, make = DERIVED[name]
                derived = make(table)
            save(con, name, table)
            line = f"{name}: {notes['baris_raw']} baris raw -> {len(table)} baris bersih"
            if "kolom_tidak_ada" in notes:
                line += f" (kolom tidak ada di file: {notes['kolom_tidak_ada']})"
            print(line)
            if name in DERIVED:
                save(con, derived_name, derived)
                print(f"  {derived_name}: {len(derived)} baris, hasil terakhir per sampel")
        spec = load_spec_limits()
        save(con, "spec_limits", spec)
        print(f"spec_limits: {len(spec)} baris dari config/spek_produk.csv")
    print(f"\nDatabase: {DB_PATH}")


if __name__ == "__main__":
    main()
