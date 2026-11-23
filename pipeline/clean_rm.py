"""Clean the raw material receiving log (QC incoming): one row per delivery."""

import pandas as pd

from common import (apply_limits, clean_lot, clean_time, drop_exact_duplicates, load_padanan, parse_date,
                    read_config, read_source, squash, to_number)

TESTS = ["ffa", "pv", "moisture", "color_red", "de", "ph", "protein", "fat", "solubility", "tpc"]
NUMBERS = [f"{who}_{test}" for test in TESTS for who in ("coa", "qc")]
DECISION = {
    "accept": "Accept", "terima": "Accept", "diterima": "Accept", "ok": "Accept",
    "conditional": "Conditional", "cond": "Conditional", "okbersyarat": "Conditional",
    "diterimabersyarat": "Conditional",
    "reject": "Reject", "tolak": "Reject", "ditolak": "Reject",
}


def clean_rm_receiving(production=None):
    """production is not used, the argument is there so every cleaner is called the same way."""
    df, notes = read_source("rm_receiving")

    # 1. the same row exported twice
    df = drop_exact_duplicates(df, notes)

    # 2. dates: three formats and Excel serial numbers in one column
    day = parse_date(df["received_date"])
    notes["tanggal_tidak_terbaca"] = int(day.isna().sum())
    df["received_at"] = day + pd.to_timedelta(clean_time(df["received_time"]).fillna("00:00") + ":00")
    df["qc_release_date"] = parse_date(df["qc_release_date"]).dt.strftime("%Y-%m-%d")

    # 3. material. The code is sometimes empty, the internal lot prefix always says which material it is.
    df["internal_lot"] = clean_lot(df["internal_lot"])
    materials = pd.DataFrame(read_config("padanan_bahan.csv")).set_index("awalan_lot")
    prefix = df["internal_lot"].str.split("-").str[0]
    notes["kode_bahan_dari_lot"] = int(df["material_code"].isna().sum())
    df["material_code"] = df["material_code"].str.strip().fillna(prefix.map(materials["material_code"]))
    df["material_name"] = df["material_name"].str.strip().fillna(prefix.map(materials["material_name"]))

    # 4. supplier typed by hand in many ways, matched through padanan_supplier.csv
    suppliers = pd.DataFrame(read_config("padanan_supplier.csv")).set_index("tulisan")
    key = squash(df["supplier_raw"])
    df["supplier_id"] = key.map(suppliers["supplier_id"])
    df["supplier_name"] = key.map(suppliers["supplier_name"])
    notes["supplier_tidak_dikenal"] = int((df["supplier_raw"].notna() & df["supplier_id"].isna()).sum())

    # 5. quantity: some rows in ton with a decimal comma
    qty = to_number(df["qty"])
    in_ton = df["unit"].str.strip().str.lower() == "ton"
    df["qty_kg"] = (qty.where(~in_ton, qty * 1000)).round().astype("Int64")
    notes["qty_dalam_ton"] = int(in_ton.sum())

    # 6. test results. '-' and 'lihat COA' become empty.
    for col in NUMBERS:
        df[col] = to_number(df[col])
    apply_limits(df, "rm_receiving", notes)

    # 7. decision and inspector
    df["decision"] = squash(df["decision"]).map(DECISION)
    notes["keputusan_tidak_dikenal"] = int(df["decision"].isna().sum())
    staff = load_padanan("padanan_staf.csv", "tulisan", "nama")
    first = df["inspector"].str.strip().str.lower().str.split().str[0]
    df["inspector"] = first.map(staff).fillna(df["inspector"])

    notes["baris_bersih"] = len(df)
    notes["lot_ganda"] = int(df["internal_lot"].duplicated().sum())
    columns = ["internal_lot", "received_at", "material_code", "material_name", "supplier_id", "supplier_name",
               "supplier_lot", "qty_kg"] + NUMBERS + ["decision", "remarks", "inspector", "qc_release_date",
                                                     "source_file"]
    return df[columns].sort_values("received_at").reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_rm_receiving()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
