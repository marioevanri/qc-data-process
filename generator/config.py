# All knobs for the synthetic QC factory live here.
# Everything is fictional: company, grades, suppliers, people, specs.
# Tweak the numbers to match what you see on the floor, that's the point of this file.

from datetime import date

SEED = 42
START_DATE = date(2025, 1, 1)
END_DATE = date(2026, 6, 30)

COMPANY = "PT Sari Krimer Nusantara"
COMPANY_SHORT = "SKN"

# NIRS spectrum grid (nm). Step 10 keeps the file small, drop to 2 if you want finer spectra.
NIRS_WL = (1100, 2500, 10)

# Reconstituted solution used for viscosity and Brix (QC protocol in SOP-QC-007)
RECON_CONC_PCT = 20.0

# Production lines
LINES = {
    "P1": {"name": "Plant 1", "grades": ["NDC-35", "NDC-28P"], "mixes_per_day": (9, 12),
           "mix_kg": (3200, 3800), "runs_sunday": 0.6},
    "P2": {"name": "Plant 2", "grades": ["NDC-28P", "FMP-26"], "mixes_per_day": (7, 10),
           "mix_kg": (3000, 3600), "runs_sunday": 0.0},
    "RT": {"name": "Line Retail", "grades": ["CRM-RT", "MLK-RT"], "mixes_per_day": (3, 6),
           "mix_kg": (800, 1200), "runs_sunday": 0.0},
}

# Products. Specs are QC release specs, targets are what the formula aims for.
# visc_base = expected viscosity (cP) of the 20% solution at 25 C when everything is normal.
PRODUCTS = {
    "NDC-35": dict(code="31", name="Krimer Nabati 35", segment="B2B", oil="RM-OIL-HCO",
                   protein_src="RM-CAS", fat=35.0, protein=2.2, moisture=2.4, visc_base=4.6,
                   bulk=0.45, ph=7.0, coffee_test=True, control_days=90,
                   spec=dict(fat=(33.5, 36.5), protein_min=1.8, moisture_max=3.5, visc=(3.8, 5.6),
                             bulk=(0.40, 0.52), solub_max=0.5, wett_max=60, L_min=92.0,
                             ph=(6.7, 7.3), tpc_max=5000, ym_max=50)),
    "NDC-28P": dict(code="34", name="Krimer Nabati 28 Palm", segment="B2B", oil="RM-OIL-PO",
                    protein_src="RM-CAS", fat=28.0, protein=2.5, moisture=2.5, visc_base=4.2,
                    bulk=0.48, ph=7.0, coffee_test=True, control_days=30,
                    spec=dict(fat=(26.5, 29.5), protein_min=2.0, moisture_max=3.5, visc=(3.4, 5.0),
                              bulk=(0.42, 0.55), solub_max=0.5, wett_max=60, L_min=92.0,
                              ph=(6.7, 7.3), tpc_max=5000, ym_max=50)),
    "FMP-26": dict(code="47", name="Filled Milk Powder 26", segment="B2B", oil="RM-OIL-PO",
                   protein_src="RM-SMP", fat=26.0, protein=18.0, moisture=2.4, visc_base=6.5,
                   bulk=0.52, ph=6.7, coffee_test=False, control_days=30,
                   spec=dict(fat=(25.0, 27.5), protein_min=16.5, moisture_max=3.0, visc=(5.5, 7.6),
                             bulk=(0.46, 0.60), solub_max=1.0, wett_max=90, L_min=90.0,
                             ph=(6.4, 6.9), tpc_max=10000, ym_max=50)),
    "CRM-RT": dict(code="61", name="Krimer Sachet Retail", segment="Retail", oil="RM-OIL-HCO",
                   protein_src="RM-CAS", fat=30.0, protein=2.0, moisture=2.4, visc_base=4.4,
                   bulk=0.47, ph=7.0, coffee_test=True, control_days=90,
                   spec=dict(fat=(28.5, 31.5), protein_min=1.6, moisture_max=3.5, visc=(3.6, 5.2),
                             bulk=(0.42, 0.54), solub_max=0.5, wett_max=60, L_min=92.0,
                             ph=(6.7, 7.3), tpc_max=5000, ym_max=50)),
    "MLK-RT": dict(code="62", name="Susu Bubuk Retail", segment="Retail", oil="RM-OIL-PO",
                   protein_src="RM-SMP", fat=22.0, protein=20.0, moisture=2.4, visc_base=7.0,
                   bulk=0.53, ph=6.7, coffee_test=False, control_days=30,
                   spec=dict(fat=(20.5, 23.5), protein_min=18.5, moisture_max=3.0, visc=(6.0, 8.2),
                             bulk=(0.46, 0.60), solub_max=1.0, wett_max=90, L_min=90.0,
                             ph=(6.4, 6.9), tpc_max=10000, ym_max=50)),
}

# Spec revision: NDC-28P moisture max tightened from this date (Spec Rev B)
SPEC_REVISIONS = [
    dict(grade="NDC-28P", param="moisture_max", old=3.5, new=3.2, effective=date(2025, 12, 1), rev="B"),
]

# Raw materials and suppliers. share = how often that supplier delivers.
MATERIALS = {
    "RM-OIL-HCO": dict(name="Hydrogenated Coconut Oil", unit_lot_kg=(20000, 24000), every_days=3,
                       suppliers={"SUP01": 0.75, "SUP02": 0.25}),
    "RM-OIL-PO": dict(name="RBD Palm Oil", unit_lot_kg=(20000, 24000), every_days=2,
                      suppliers={"SUP03": 0.7, "SUP04": 0.3}),
    "RM-GSS": dict(name="Glucose Syrup Solids DE 30", unit_lot_kg=(20000, 25000), every_days=1,
                   suppliers={"SUP05": 0.6, "SUP06": 0.4}),
    "RM-CAS": dict(name="Sodium Caseinate", unit_lot_kg=(8000, 10000), every_days=7,
                   suppliers={"SUP07": 1.0}),
    "RM-SMP": dict(name="Skim Milk Powder", unit_lot_kg=(15000, 20000), every_days=4,
                   suppliers={"SUP09": 0.6, "SUP10": 0.4}),
}

SUPPLIERS = {
    "SUP01": dict(name="PT Kelapa Mas Indah", country="Indonesia"),
    "SUP02": dict(name="Sinar Oleo Sdn Bhd", country="Malaysia"),
    "SUP03": dict(name="PT Minyak Sawit Jaya", country="Indonesia"),
    "SUP04": dict(name="PT Agro Palma Lestari", country="Indonesia"),
    "SUP05": dict(name="PT Gula Pati Nusantara", country="Indonesia"),
    "SUP06": dict(name="Qingdao Sweetech Co., Ltd", country="China"),
    "SUP07": dict(name="Caseina Lowlands B.V.", country="Netherlands"),
    "SUP08": dict(name="Huaxin Caseo Biotech", country="China"),
    "SUP09": dict(name="Southern Cross Dairy Ingredients Ltd", country="New Zealand"),
    "SUP10": dict(name="Alpenmilch Pulver GmbH", country="Germany"),
    "SUP11": dict(name="Pampa Dairy Powders S.A.", country="Argentina"),
}

# Messy spellings people actually type for each supplier
SUPPLIER_ALIASES = {
    "SUP01": ["PT. Kelapa Mas Indah", "Kelapa Mas Indah", "KMI", "PT Kelapa Mas", "PT Klapa Mas Indah"],
    "SUP02": ["Sinar Oleo", "SINAR OLEO SDN BHD", "Sinar Oleo Sdn. Bhd.", "SOSB"],
    "SUP03": ["PT. Minyak Sawit Jaya", "Minyak Sawit Jaya", "MSJ", "PT Minyk Sawit Jaya", "PT MSJ"],
    "SUP04": ["PT. Agro Palma Lestari", "Agro Palma", "APL", "PT Agro Palma Lestri"],
    "SUP05": ["PT. Gula Pati Nusantara", "Gula Pati", "GPN", "PT Gula Pati Nusantra"],
    "SUP06": ["Qingdao Sweetech", "QINGDAO SWEETECH CO LTD", "Sweetech", "Qingdao Sweettech"],
    "SUP07": ["Caseina Lowlands", "Caseina BV", "CASEINA LOWLANDS B.V", "Caseina"],
    "SUP08": ["Huaxin Caseo", "HUAXIN CASEO BIOTECH", "Huaxin", "Huaxin Biotech"],
    "SUP09": ["Southern Cross Dairy", "SCDI", "Southern Cross Dairy Ingr. Ltd", "Southern Cross"],
    "SUP10": ["Alpenmilch", "ALPENMILCH PULVER GMBH", "Alpenmilch Pulver", "Alpen Milch"],
    "SUP11": ["Pampa Dairy", "PAMPA DAIRY POWDERS SA", "Pampa Dairy Powders", "Pampa"],
}

CUSTOMERS = {
    "C01": dict(name="PT Kopi Instan Sejahtera", segment="B2B", grades=["NDC-35", "NDC-28P"]),
    "C02": dict(name="PT Minuman Segar Abadi", segment="B2B", grades=["NDC-28P", "FMP-26"]),
    "C03": dict(name="PT Roti Mentari Pagi", segment="B2B", grades=["FMP-26"]),
    "C04": dict(name="CV Kedai Kopi Rakyat", segment="B2B", grades=["NDC-35"]),
    "C05": dict(name="PT Distribusi Retail Jatim", segment="Retail", grades=["CRM-RT", "MLK-RT"]),
    "C06": dict(name="PT Mitra Swalayan Nusantara", segment="Retail", grades=["CRM-RT", "MLK-RT"]),
}

# QC people. bias = tendency in scale steps, noise = sd in scale steps,
# deadband = how far off the reference before they call it not-0 (bigger = more lenient).
KIMFIS_ANALYSTS = {
    "AN01": dict(name="Andi Prasetyo", bias=0.00, noise=0.17, deadband=0.50, offflavor_sens=0.55,
                 start=None, end=None),
    "AN02": dict(name="Dewi Lestari", bias=-0.10, noise=0.16, deadband=0.48, offflavor_sens=0.65,
                 start=None, end=None),
    "AN03": dict(name="Rizky Maulana", bias=0.08, noise=0.21, deadband=0.62, offflavor_sens=0.40,
                 start=None, end=None),
    "AN04": dict(name="Sari Wulandari", bias=0.04, noise=0.17, deadband=0.52, offflavor_sens=0.60,
                 start=None, end=None),
    "AN05": dict(name="Bayu Saputra", bias=-0.05, noise=0.18, deadband=0.50, offflavor_sens=0.50,
                 start=None, end=date(2025, 10, 3)),
    # New hire replacing AN05. Noisy and lenient while still in training.
    "AN06": dict(name="Fitri Handayani", bias=0.12, noise=0.18, deadband=0.55, offflavor_sens=0.45,
                 start=date(2025, 10, 6), end=None, training_until=date(2025, 12, 15),
                 training_noise=0.28),
}

VERIFIKATORS = {
    "VR01": dict(name="Hendra Gunawan", bias=0.00, noise=0.15, deadband=0.50, offflavor_sens=0.90),
    "VR02": dict(name="Lina Marlina", bias=-0.04, noise=0.17, deadband=0.48, offflavor_sens=0.85),
}

# Share of samples the verifikator re-checks at H+1 (SOP-QC-005 Rev 02 vs Rev 03)
VERIF_SHARE = [(date(2025, 1, 1), 0.25), (date(2026, 1, 5), 0.30)]

# Days with no production at all (plant shutdown around Lebaran and a few national holidays)
SHUTDOWNS = [
    (date(2025, 3, 28), date(2025, 4, 6)),
    (date(2026, 3, 18), date(2026, 3, 26)),
]
HOLIDAYS = [date(2025, 1, 1), date(2025, 8, 17), date(2025, 12, 25), date(2026, 1, 1)]

# Rainy season months (humid air, moisture pickup, caking complaints)
WET_MONTHS = [11, 12, 1, 2, 3]

# Hidden incidents are drawn per seed in events.py (spoiler). generate.py fills these in at run time.
EVENTS = []
NIRS_BIAS_FIX_DATE = None   # NIRS model bias correction after a lamp change
SOP_HOLD_REV05_DATE = None  # SOP-QC-012 Rev 05 after a CIP recall, if there was one

# How dirty the raw layer gets. 0 turns a mess type off.
MESS = dict(
    exact_duplicate=0.012,       # same row exported twice
    near_duplicate=0.008,        # re-entered with a corrected value, both rows kept
    missing_cell=0.025,          # random blanks in measured columns
    decimal_comma=0.06,          # "2,45" instead of 2.45 (some analysts only)
    decimal_shift=0.003,         # 4.2 typed as 42
    text_in_numeric=0.01,        # "ND", "-", "retest", "tdk diuji"
    batch_typo=0.015,            # transposed digit, lowercase, spaces
    grade_variant=0.15,          # "NDC 28P", "ndc-28p", ...
    supplier_alias=0.45,         # supplier typed by hand
    analyst_variant=0.20,        # "Andi", "andi", "AN01", "Andi P."
    date_format_mix=0.20,        # mixed date formats in receiving
    excel_serial_date=0.02,      # 45839 instead of a date
    logger_gap_days=6,           # number of logger outages
    stuck_sensor_events=5,       # sensor frozen at one value for hours
    sentinel_value=0.002,        # 0 or 9999 from the logger
    wrong_sample_swap=0.002,     # two sample codes swapped
    late_entry=0.05,             # entered days after the test
)
