# Synthetic QC Factory: dairy and creamer

A generator for realistic, messy quality control data from a fictional powdered creamer and milk factory, covering raw material receiving, production, lab, NIRS, sensory, micro, release, shipment and customer complaints. It also writes the text documents a QC department produces (SOPs, specs, NCRs, memos, shift logbooks, meeting notes) so the same factory can be used for RAG work.

I built it because real QC data can't go on a public GitHub, and most public datasets are far too clean to practice on.

Everything here is fictional: PT Sari Krimer Nusantara, its grades, suppliers, customers and staff.

## Read this first

The relationships between raw materials, process, composition and sensory are assumptions written in `quality.py`, loosely based on how spray-dried creamer behaves. A model trained on this data learns those assumptions, nothing more. Accuracy numbers from this data say nothing about a real plant.

What it is good for: practicing the unglamorous part of the job (cleaning, joining data from departments that don't talk to each other, schema changes, ambiguous records), building pipelines end to end, and evaluating methods against a known answer key, which real factory data never gives you.

## Quick start

```bash
pip install -r requirements.txt
python generate.py            # about 2 to 3 minutes, about 85 MB
python generate.py --seed 7   # a different factory with different hidden incidents
```

On the same machine the same seed gives the same data, so `data/` and `docs/` stay out of git and are regenerated instead. Across machines that hasn't held: seed 42 gave 182 documents on one and 169, with other batch numbers, in a different environment. The cause isn't found yet, probably the Python or numpy version. For a blind early warning test, pick a seed nobody has looked at and don't print what it drew.

## What you get

| Folder | Contents |
|---|---|
| `data/raw/` | Files as each department would export them. This is what you work with. |
| `data/clean/` | The same records, recorded correctly. Answer key for your cleaning pipeline. |
| `data/truth/` | Hidden events, product formulas and true values. Answer key for early warning and modeling. Never use as features. |
| `docs/` | About 200 Indonesian documents for RAG. |

Raw files by department:

| Path | Source | Notes |
|---|---|---|
| `rm_receiving/Log_Penerimaan_RM_<year>.csv` | QC raw material | COA vs QC results, Accept / Conditional / Reject |
| `production/Production_Mix_Log.csv` | Production | English headers, own mix numbering, lot numbers per mix |
| `production/logger/Dryer_<line>_<month>.csv` | Dryer PLC logger | every 30 minutes |
| `qc_lab/KimFis_<month>.csv` | KimFis lab | moisture, fat, protein, viscosity, Brix, bulk density, solubility, wettability, color, pH, coffee test |
| `nirs/NIRS_Export_<year>.csv`, `NIRS_Spectra_<year>.csv.gz` | NIRS instrument | predictions plus spectra 1100 to 2500 nm |
| `sensory/Sensory_KimFis_<month>.csv` | KimFis analyst on shift | creamy, mouthfeel, milky, sweetness vs a reference control |
| `sensory/Verifikasi_H1.csv` | Verifikator, next day | re-check of a share of samples |
| `sensory/Log_Kontrol_Sensory.csv` | QC | reference control history |
| `sensory/Transisi_Retail.csv` | QC | minute by minute samples after a grade change on the retail line |
| `micro/Hasil_Mikro_<year>.csv` | Micro lab | TPC, coliform, yeast and mold, MS / TMS |
| `release/Status_Release.csv` | QC | status history per mix |
| `warehouse/Pengiriman_<year>.csv` | Warehouse | delivery orders |
| `complaints/Komplain_Customer.csv` | Customer service | lot reference as written by the customer |

Column meanings for the clean tables are in `DATA_DICTIONARY.md`.

## The factory

Three lines (P1, P2, RT retail), five grades, around 25 mixes a day over 18 months (January 2025 to June 2026), about 10,000 mixes and 30,000 samples. Each mix is sampled at three points: A1 start, A2 middle, A3 end. Batch number is YYMMDD + grade code + line, for example `25090834P2`.

Raw materials are hydrogenated coconut oil, RBD palm oil, glucose syrup solids, sodium caseinate and skim milk powder, each traceable by lot to the mix that used it. Every sample gets chem-phys tests, a NIRS scan and a sensory score from the KimFis analyst on shift, compared against a reference control that is replaced every 30 or 90 days. A verifikator re-tastes 25 to 30 % of samples the next day plus every TP2 and TP3. Micro is tested per batch. Release decisions, shipments and complaints follow from all of that.

## How messy raw is

- Each department has its own habits: QC writes Indonesian headers and dd/mm/yyyy, production writes English headers, the micro lab writes MS / TMS and TPC as `1,7 x 10^2`.
- Production numbers mixes per line per day (1, 2, 3) and writes batches as `250908/34/P2`, QC letters mixes per batch (A, B, C). Joining them is a real task.
- Schema changes mid-stream: lab sheets rename columns and add Line and Retest from January 2026, sensory switches from word labels to numbers on 5 January 2026 after an SOP revision.
- Three monthly lab files were saved from Excel with Indonesian regional settings (semicolon separator, decimal comma).
- Decimal commas from specific people, shifted decimals, text in numeric cells (`ND`, `-`, `tdk diuji`), one analyst who records bulk density in g/L.
- Suppliers, grades, analysts and customers spelled several ways, batch number typos, Excel serial dates.
- Retests sometimes marked and sometimes not, exact and near duplicates, a few swapped samples.
- Night shift: production date vs calendar date, finish times past midnight with no date.
- Logger outages, frozen sensors, 0 and 9999 sentinel values, readings duplicated after a restart.
- NIRS sample names typed by hand, rescans, junk scans of trials and competitor samples.
- Some release rows cover a whole batch (`ALL`, `A-F`) instead of one mix.
- Retail transitions have no transition ID or sequence, only sample clock times.
- Customers give lot references that are missing, partial or wrong.

`data/truth/raw_row_map.csv` maps every raw row back to its clean record and lists which mess was applied, so you can score your cleaning.

## The answer key

Each seed draws its own hidden incidents: which ones happen (usually 7 to 11 out of 12 possible kinds), when, on which line, grade or supplier, and how strong the effect is. Instrument problems, process faults, raw material changes and unannounced formula changes are all in the pool. The QC data never states an incident, it only shows its effects, and the documents only describe what people knew at the time.

`data/truth/` holds the drawn incidents, RND's recipes and the true values behind every measurement. For an honest early warning test, move the whole folder out of the project and only bring back `raw_row_map.csv` for scoring your cleaning. `ANSWER_KEY.md`, `events.py`, `formula.py` and `documents.py` describe the incidents too, and `docs/` has memos written after the fact, so leave those for after your detector is scored.

`rag_eval_questions.csv` has around 30 questions (the exact set depends on the seed) with expected answers and a route: `rag`, `sql`, `rag+sql`, or `refuse` for questions the documents can't answer.

## Projects this supports

1. QC knowledge assistant. RAG over `docs/` plus text-to-SQL over the cleaned tables, with a router between them. The documents include superseded SOP revisions and NCRs whose first analysis was wrong, so retrieval has to respect dates and document status. The documents are in Indonesian, pick a multilingual embedding model.
2. Early warning. Detect material, process and formula changes from QC and NIRS data before customers complain. Score by detection lead time and false alarms against `events.csv`.
3. Creamy and mouthfeel prediction. Features from lab, NIRS and process, labels from KimFis sensory. Expect a low ceiling: one analyst per shift, personal bias, and a reference control that drifts with production. `sample_truth.csv` lets you separate how much of the error is the model and how much is the label.

## Tuning

`config.py` holds dates, line capacity, product specs, suppliers, analyst bias and noise, and the mess rates. Set any mess rate to 0 to turn that kind of mess off. `events.py` draws the hidden incidents and `formula.py` holds the recipes. Both are part of the answer key.

## Known simplifications

- NIRS spectra are Gaussian absorption bands on a sloped baseline with scatter, not real chemometrics.
- One analyst per shift tastes every sample, there is no panel.
- Process values are per mix, the logger smooths them into 30 minute readings.
- No pallets, warehouse stock or packaging line.
- Recipes have six ingredient groups, flavors, vitamins and minor additives are left out.
