"""Clean the production mix log: one row per mix, with the keys every other table joins on."""

import pandas as pd

from common import RAW_DIR, clean_batch, clean_grade, clean_lot, fix_decimal_shift, read_raw, to_number

# highest value that still makes sense, anything above is a slipped decimal point
HIGHEST = {"inlet_temp": 300, "outlet_temp": 150, "homog_p1_bar": 400, "homog_p2_bar": 100, "emulsion_temp": 100}

RENAME = {
    "Line": "line", "Qty (kg)": "mix_kg", "Oil Lot": "oil_lot", "GSS Lot": "gss_lot", "Protein Lot": "protein_lot",
    "Inlet (C)": "inlet_temp", "Outlet (C)": "outlet_temp", "Homog P1 (bar)": "homog_p1_bar",
    "Homog P2 (bar)": "homog_p2_bar", "Feed TS (%)": "feed_solids", "Emul Temp (C)": "emulsion_temp",
    "Operator": "operator", "Remarks": "remarks",
}


def clean_production_mix_log():
    raw = read_raw(RAW_DIR / "production" / "Production_Mix_Log.csv")
    notes = {"baris_raw": len(raw)}

    # 1. the same row exported twice
    df = raw.drop_duplicates().rename(columns=RENAME).copy()
    notes["duplikat_dibuang"] = len(raw) - len(df)

    # 2. text columns people type in different ways
    df["line"] = df["line"].str.strip().str.upper()
    df["grade"] = clean_grade(df["Product"])
    df["batch_no"] = clean_batch(df["Batch"])
    for col in ["oil_lot", "gss_lot", "protein_lot"]:
        df[col] = clean_lot(df[col])

    # 3. dates and times. A production day runs 07:00 to 07:00, so a mix that starts
    #    at 02:00 belongs to the previous date but happens on the next calendar day.
    df["prod_date"] = pd.to_datetime(df["Date"], format="%d-%m-%Y")
    start_time = pd.to_timedelta(df["Start"] + ":00")
    end_time = pd.to_timedelta(df["Finish"] + ":00")
    after_midnight = start_time < pd.Timedelta(hours=7)
    df["start"] = df["prod_date"] + start_time + pd.to_timedelta(after_midnight.astype(int), unit="D")
    df["end"] = df["start"].dt.normalize() + end_time
    df.loc[df["end"] < df["start"], "end"] += pd.Timedelta(days=1)
    hour = df["start"].dt.hour
    df["shift"] = 3
    df.loc[(hour >= 7) & (hour < 15), "shift"] = 1
    df.loc[(hour >= 15) & (hour < 23), "shift"] = 2

    # 4. mix letter. "Mix No" counts mixes per line per day, but the lab and sensory sheets
    #    use a letter that counts mixes inside one batch number: first mix of the batch is A.
    df = df.sort_values(["batch_no", "start"])
    order = df.groupby("batch_no").cumcount()
    df["mix_letter"] = order.map(lambda n: chr(ord("A") + n))
    df["mix_id"] = df["batch_no"] + "-" + df["mix_letter"]

    # 5. numbers
    df["mix_kg"] = to_number(df["mix_kg"]).astype("Int64")
    df["feed_solids"] = to_number(df["feed_solids"])
    for col, highest in HIGHEST.items():
        df[col], notes[f"desimal_geser_{col}"] = fix_decimal_shift(to_number(df[col]), highest)
        notes[f"kosong_{col}"] = int(df[col].isna().sum())

    df["prod_date"] = df["prod_date"].dt.strftime("%Y-%m-%d")
    notes["baris_bersih"] = len(df)
    notes["mix_id_ganda"] = int(df["mix_id"].duplicated().sum())
    columns = ["mix_id", "batch_no", "prod_date", "line", "grade", "mix_letter", "shift", "start", "end", "mix_kg",
               "oil_lot", "gss_lot", "protein_lot", "inlet_temp", "outlet_temp", "homog_p1_bar", "homog_p2_bar",
               "feed_solids", "emulsion_temp", "operator", "remarks"]
    return df[columns].reset_index(drop=True), notes


if __name__ == "__main__":
    table, notes = clean_production_mix_log()
    for name, value in notes.items():
        print(f"{name:<32}{value}")
    print(table.head())
