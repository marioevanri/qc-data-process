"""Clean the warehouse delivery log: one row per delivery order (DO)."""

from clean_production import production_or_none
from common import (clean_grade, drop_exact_duplicates, load_padanan, nearest_batch, parse_date, read_source,
                    squash, to_number)


def customer_lookup(series):
    """'PT. KIS', 'Kopi Instan Sejahtera' and 'KIS' all become C01 through padanan_customer.csv."""
    ids = load_padanan("padanan_customer.csv", "tulisan", "customer_id")
    names = load_padanan("padanan_customer.csv", "tulisan", "customer_name")
    key = squash(series)
    return key.map(ids), key.map(names)


def clean_shipments(production=None):
    """production: the clean production log, or None to load it here (or to work without it)."""
    if production is None:
        production = production_or_none()
    df, notes = read_source("shipments")
    df = drop_exact_duplicates(df, notes)

    # 1. who and what
    df["ship_date"] = parse_date(df["ship_date"])
    df["customer_id"], df["customer_name"] = customer_lookup(df["customer_raw"])
    notes["customer_tidak_dikenal"] = int(df["customer_id"].isna().sum())
    df["grade"] = clean_grade(df["grade"])

    # 2. batch. The delivery note has no production date. Finished goods here ship within
    #    17 days of production, so a batch made more than 30 days before shipping is a typo
    #    and is matched to the most similar batch of the same grade made in that window.
    nearest_batch(df, production, "ship_date", days=30, notes=notes)

    # 3. mixes as 'A,B,C', quantities as numbers
    df["mixes"] = df["mixes"].str.upper().str.replace(r"[^A-Z,]", "", regex=True)
    df["qty_kg"] = to_number(df["qty_kg"]).round().astype("Int64")
    df["packs"] = to_number(df["packs"]).round().astype("Int64")

    df["ship_date"] = df["ship_date"].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    notes["do_ganda"] = int(df["do_no"].duplicated().sum())
    columns = ["do_no", "ship_date", "customer_id", "customer_name", "batch_no", "grade", "mixes", "qty_kg", "packs",
               "source_file"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_shipments()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
