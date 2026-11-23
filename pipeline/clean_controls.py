"""Clean the sensory control log: one row per reference control and the dates it was in use."""

from common import clean_generic


def clean_sensory_controls(production=None):
    """The sheet is tidy, so clean_generic does the work. production isn't used, it's only
    there so build_db can call every cleaner the same way."""
    df, notes = clean_generic("sensory_controls")
    # kept past its due date. A control still in use when the log was exported has no
    # replacement date yet, so whether it will be extended isn't known and stays empty.
    known = df["end_use"].notna()
    df["extended"] = (df["end_use"] > df["due_date"]).where(known).astype("Int64")
    notes["diperpanjang"] = int((df["extended"] == 1).sum())
    notes["masih_dipakai"] = int((~known).sum())
    columns = ["control_id", "grade", "source_batch", "start_use", "due_date", "end_use", "extended", "note",
               "source_file"]
    return df[columns], notes


if __name__ == "__main__":
    table, notes = clean_sensory_controls()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
