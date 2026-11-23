"""Clean the release log: one row per status change of one mix."""

import pandas as pd

from clean_production import production_or_none
from common import (clean_grade, drop_exact_duplicates, load_padanan, nearest_batch, parse_date, production_day,
                    read_source, squash)

PENDING = {"QUARANTINE", "HOLD"}


def mixes_written(text):
    """'C' is mix C, 'E-G' is mixes E and G decided together (not E to G). 'ALL' is filled in later."""
    text = str(text).strip().upper()
    if text == "ALL":
        return ["ALL"]
    return [m for m in text.replace(" ", "").split("-") if m]


def resolve_all(df, production, notes):
    """'ALL' means the rest of the batch: the mixes still waiting (QUARANTINE or HOLD) at that
    moment that get no decision anywhere else in the log. Without a production log only mixes
    that show up elsewhere in the log are known. When one batch has two ALL rows the first one
    takes all of them, the sheet doesn't say how they were split."""
    if production is not None:
        mixes_of = production.groupby("batch_no")["mix_letter"].apply(sorted).to_dict()
    else:
        mixes_of = df[df["mix"] != "ALL"].groupby("batch_no")["mix"].apply(lambda m: sorted(set(m))).to_dict()
    rows, resolved = [], {}
    for i in df.index[df["mix"] == "ALL"].sort_values():
        batch, when = df.at[i, "batch_no"], df.at[i, "status_time"]
        log = df[(df["batch_no"] == batch) & (df["mix"] != "ALL")]
        last = log[log["status_time"] < when].sort_values("status_time").groupby("mix")["status"].last()
        decided_later = set(log.loc[log["status_time"] > when, "mix"])
        taken = {m for r in rows if r["batch_no"] == batch for m in r["mixes"]}
        waiting = [m for m in mixes_of.get(batch, [])
                   if last.get(m, "QUARANTINE") in PENDING and m not in decided_later and m not in taken]
        rows.append({"batch_no": batch, "mixes": waiting})
        resolved[i] = waiting or ["ALL"]
    notes["baris_all"] = len(rows)
    notes["all_tidak_terurai"] = sum(1 for r in rows if not r["mixes"])
    return [resolved.get(i, m) for i, m in zip(df.index, df["mix"])]


def clean_release_history(production=None):
    """production: the clean production log, or None to load it here (or to work without it)."""
    if production is None:
        production = production_or_none()
    df, notes = read_source("release_history")
    df = drop_exact_duplicates(df, notes)

    # 1. when, which batch, which status
    df["status_time"] = parse_date(df["status_time"])
    df["grade"] = clean_grade(df["grade"])
    statuses = load_padanan("padanan_status.csv", "tulisan", "status")
    df["status"] = squash(df["status"]).map(statuses).fillna(df["status"].str.strip())
    notes["status_tidak_dikenal"] = int((~df["status"].isin(set(statuses.values()))).sum())
    # batch typos are matched like in shipments. QUARANTINE is set by the system right after
    # packing, so that batch was made at most 2 days before. Later decisions come within 30.
    # The window is counted in production days, 02:30 still belongs to the day before.
    df["status_day"] = production_day(df["status_time"])
    quarantine = df["status"] == "QUARANTINE"
    fixed, unknown = 0, 0
    for part, days in ((quarantine, 2), (~quarantine, 30)):
        rows, part_notes = df[part].copy(), {}
        nearest_batch(rows, production, "status_day", days=days, notes=part_notes)
        df.loc[part, "batch_no"] = rows["batch_no"]
        fixed += part_notes.get("batch_diperbaiki", 0)
        unknown += part_notes.get("batch_tidak_dikenal", 0)
    notes["batch_diperbaiki"], notes["batch_tidak_dikenal"] = fixed, unknown
    df["decided_by"] = df["decided_by"].str.strip()

    # 2. one row per mix. 'E-G' becomes two rows, 'ALL' becomes the mixes it stands for.
    df["mix"] = df["mix"].map(mixes_written)
    df = df.explode("mix").reset_index(drop=True)
    df["mix"] = resolve_all(df, production, notes)
    df = df.explode("mix").reset_index(drop=True)

    df["line"] = df["batch_no"].str[-2:]
    if production is not None:
        df["grade"] = df["batch_no"].map(production.drop_duplicates("batch_no").set_index("batch_no")["grade"]).fillna(df["grade"])
    df["mix_id"] = df["batch_no"] + "-" + df["mix"]
    df = df.sort_values(["status_time", "mix_id"], kind="stable")
    notes["baris_bersih"] = len(df)
    columns = ["mix_id", "batch_no", "grade", "line", "status_time", "status", "reason", "decided_by", "source_file"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_release_history()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
