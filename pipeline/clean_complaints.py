"""Clean the customer complaint log: one row per complaint, traced to a batch and a delivery."""

import re

import pandas as pd

from clean_shipments import clean_shipments, customer_lookup
from common import (DOC_DIR, clean_batch, clean_grade, drop_exact_duplicates, parse_date, read_config, read_source,
                    to_number, typo_distance)

BATCH = re.compile(r"(\d{8})\s*(P1|P2|RT)?", re.IGNORECASE)
# the trace in the investigation report: '| Batch | 25030462RT (DO DO-2503-00277) |'
REPORT_TRACE = re.compile(r"\|\s*Batch\s*\|\s*(\w+)\s*\(DO\s*(DO-[\w-]+)\)")


def category_of(text, rules):
    """First keyword from kategori_komplain.csv found in the complaint, '*' is the fallback."""
    words = str(text).lower()
    for rule in rules:
        if rule["kata"] != "*" and rule["kata"] in words:
            return rule["kategori"]
    return next((r["kategori"] for r in rules if r["kata"] == "*"), None)


def traced_in_reports():
    """complaint_id -> (batch, DO) from the investigation reports, where QA wrote down the
    batch it traced the complaint to. No reports folder means no traces."""
    traces = {}
    for path in sorted((DOC_DIR / "complaints").glob("INV-CMP-*.md")):
        found = REPORT_TRACE.search(path.read_text(encoding="utf-8"))
        if found:
            traces[path.stem.replace("INV-", "")] = (found[1].upper(), found[2].upper())
    return traces


def batch_from_lot(text, customer_shipments):
    """The lot the customer read off the bag: 'Lot: 25010862RT', 'LOT 25050331P1', '25081861rt',
    '25122034' (no line) or '26O20462RT'. It has to be a batch this customer received, so the
    match is made against their deliveries: exact, then same start, then fewest typos."""
    without_word = re.sub(r"lot", "", str(text), flags=re.IGNORECASE)
    found = BATCH.search(clean_batch(pd.Series([without_word])).iloc[0])
    if not found:
        return None
    typed = found[1] + (found[2] or "").upper()
    received = customer_shipments["batch_no"].unique()
    if typed in received:
        return typed
    starts = [b for b in received if b.startswith(typed)]
    if len(starts) == 1:
        return starts[0]
    distance = {b: typo_distance(b, typed) for b in received if len(b) == len(typed)}
    if not distance or min(distance.values()) > 2:
        return None
    closest = [b for b, d in distance.items() if d == min(distance.values())]
    return closest[0] if len(closest) == 1 else None


def clean_complaints(production=None):
    """production: the clean production log, or None to load it here (or to work without it)."""
    df, notes = read_source("complaints")
    df = drop_exact_duplicates(df, notes)
    shipments, _ = clean_shipments(production)

    # 1. who, what, when
    df["received_date"] = parse_date(df["received_date"])
    df["customer_id"], df["customer_name"] = customer_lookup(df["customer_raw"])
    notes["customer_tidak_dikenal"] = int(df["customer_id"].isna().sum())
    df["grade"] = clean_grade(df["grade"])
    rules = read_config("kategori_komplain.csv")
    df["category"] = df["description"].map(lambda text: category_of(text, rules))
    df["qty_affected_kg"] = to_number(df["qty_affected_kg"]).round().astype("Int64")
    df["status"] = df["status"].str.strip().str.capitalize()
    # an open complaint has no investigation result yet, so justified stays empty
    result = df["investigation_result"].str.strip().str.lower()
    df["justified"] = result.map({"terbukti": 1, "tidak terbukti": 0}).astype("Int64")

    # 2. which batch and which delivery. The investigation report is the trace QA made, so it
    #    comes first. Without one, the lot the customer gave is matched against what this
    #    customer received before the complaint. A delivery date from the customer
    #    ('kiriman tgl 10/05') is not used: it was 6 to 20 days off from the real delivery
    #    every time it could be checked. It stays readable in lot_text.
    reports = traced_in_reports()
    df["batch_no"], df["do_no"], df["trace_source"] = None, None, None
    for i, row in df.iterrows():
        received = shipments[(shipments["customer_id"] == row["customer_id"])
                             & (shipments["ship_date"] <= row["received_date"].strftime("%Y-%m-%d"))]
        batch, do_no, source = None, None, None
        if row["complaint_id"] in reports:
            (batch, do_no), source = reports[row["complaint_id"]], "laporan investigasi"
            # worth knowing how often the lot on the customer's bag isn't what QA traced
            from_lot = batch_from_lot(row["lot_text"], received)
            notes["lot_beda_dengan_laporan"] = notes.get("lot_beda_dengan_laporan", 0) + int(
                from_lot is not None and from_lot != batch)
        else:
            batch = batch_from_lot(row["lot_text"], received)
            source = "lot dari customer" if batch else None
        if batch and do_no is None:
            # the last delivery of that batch to this customer before the complaint
            match = received[received["batch_no"] == batch].sort_values("ship_date")
            do_no = match["do_no"].iloc[-1] if len(match) else None
        df.at[i, "batch_no"], df.at[i, "do_no"], df.at[i, "trace_source"] = batch, do_no, source
    notes["dari_laporan"] = int((df["trace_source"] == "laporan investigasi").sum())
    notes["dari_lot_customer"] = int((df["trace_source"] == "lot dari customer").sum())
    notes["batch_tidak_ketemu"] = int(df["batch_no"].isna().sum())

    df["received_date"] = df["received_date"].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    columns = ["complaint_id", "received_date", "customer_id", "customer_name", "do_no", "batch_no", "grade",
               "category", "description", "qty_affected_kg", "justified", "status", "trace_source", "lot_text"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_complaints()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
