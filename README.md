# qc-data-process

A fictional creamer and milk powder factory, taken from messy department exports to one database, and an assistant QC staff can ask about batches, raw material lots, complaints and SOPs.

I work in sensory QC at a creamer and milk powder plant. Real QC data can't go on a public GitHub, so this repo builds a fake factory that is as messy as a real one and does the work on that instead. Everything here is fictional: the company, its grades, suppliers, customers, staff and documents.

## The three parts

| Folder | What it does | Details |
|---|---|---|
| `generator/` | Generates 18 months of factory data as each department would export it (typos, mixed date formats, renamed columns, missing values), about 180 QC documents in Indonesian, and an answer key with the true values | [generator/README.md](generator/README.md) |
| `pipeline/` | Cleans 13 raw sources into one SQLite database. What changes between plants (column names, spellings, valid ranges, which sources exist) lives in CSV files under `pipeline/config`, not in the code | [PANDUAN.md](PANDUAN.md), in Indonesian |
| `assistant/` | A Streamlit chat that answers from the documents and the database. Database questions go through fixed, tested queries, not SQL written by the model | [assistant/README.md](assistant/README.md) |

## Results

**Cleaning**, scored column by column against the generator's answer key (`pipeline/check_against_key.py`). In 9 of the 13 tables no cleaned value differs from the key. Empty cells remain where the raw file had nothing readable, such as a broken sensor or a `-` instead of a number. The four tables with differences each have a reason written down in the guide: about 20 pairs of lab sample codes swapped when typed in, 4 sensory samples whose scores were never written, a TPC that Excel cut to `1.8E+0`, and two batches whose release log has two `ALL` rows without saying which mixes each one covers.

**Assistant**, every answer read and graded by hand:

| Questions | Result |
|---|---|
| Documents, holdout of 12 | 12 correct |
| Database, holdout of 9, `gemini-3.5-flash-lite`, two runs | 5 and 7 correct |
| Database, same holdout, `gemini-3.6-flash` | 6 of the 7 it answered correct |

The assistant README has the full history, including what went wrong. Two things that went wrong are worth knowing up front. Flash-lite answers changed between runs on the same questions, so one run says little. And a number formatter bug sent TPC 380 to the model as 38 through a whole round of review before it was caught.

## Run it

```bash
cd generator
pip install -r requirements.txt
python generate.py              # 2 to 3 minutes
cd ..

python pipeline/build_db.py
python pipeline/check_against_key.py

cd assistant
pip install -r requirements.txt
python eval/run_data_eval.py    # no API key needed
set GEMINI_API_KEY=your-key     # Windows; export on Linux or macOS
streamlit run app.py
```

## Before you rely on it

- The relationships between raw material, process and quality are assumptions written into the generator. Nothing learned from this data says anything about a real plant.
- The same seed has not given the same data on every machine: 182 documents on mine, 169 with other batch numbers in a different environment. The cause isn't found yet, probably the Python or numpy version. The evaluation questions in `assistant/eval` name complaints, batches and lots from my machine, so on a different machine many of them won't find their batch.
- The guide (`PANDUAN.md`) is in Indonesian because I wrote it for myself and for adapting the pipeline to real data at work. Code, comments and the other READMEs are in English. The documents, prompts and test questions are in Indonesian, like the plant they imitate.
