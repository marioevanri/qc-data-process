# QC Assistant (work in progress)

A chat assistant for QC staff of a fictional creamer and milk powder plant. It answers from about 180 QC documents: SOPs, product specs, NCRs, memos, shift logbooks, meeting notes, and complaint investigations. Every answer names the documents it came from.

This is the document half of a larger tool. Questions that need numbers from lab data (averages, counts, trends) will go through tested SQL queries on the cleaned QC database, which isn't connected yet.

> Everything here is fictional. The documents come from the synthetic data generator in `../generator`.

## How it works

1. **Split.** Each document is cut into sections (359 chunks from 182 documents), and the document title is added to every chunk.
2. **Filter revisions.** SOPs and specs exist in several revisions. The code reads the period a question is about ("Februari 2026", "15 November 2025", or no date, meaning today) and drops revisions that weren't in force then. This is plain code, not the model.
3. **Search.** BM25 keyword search with a rough Indonesian stemmer. No embeddings, no vector database. Rules (SOP, spec) and records (NCR, memo, logbook, ...) are ranked separately and the top 3 of each are kept, because records outnumber rules ten to one and would otherwise push the rule out of the results.
4. **Answer.** Gemini writes the answer from those chunks only, cites the document names, and says "Tidak ditemukan di dokumen" when the answer isn't there.

## Evaluation

Retrieval, scored without a language model (is the right document among the retrieved chunks):

| Set | Rules | Records |
|---|---|---|
| Main (25 questions with a source document) | 15 of 15 | 10 of 10 |
| Holdout (11 questions) | 6 of 6 | 5 of 5 |

Answers from `gemini-3.5-flash-lite`, each one read and checked by hand:

| Set | Prompt v2 | Prompt v3 |
|---|---|---|
| Main (31 questions) | 27 correct | 30 correct, 1 partly |
| Holdout (12 questions) | not run | 12 correct |

What went wrong along the way, and what it changed:

- With one shared ranking, "moisture limit of NDC-28P" retrieved complaint reports instead of the spec. That led to ranking rules and records separately.
- Without the stemmer, a question using "berganti" missed the memo that says "menggantikan".
- Prompt v2 answered "yes, allowed" to a question whose own quoted rule said the opposite. Prompt v3 makes the model write the rule first and the conclusion after. The keyword check had marked that wrong answer as OK, which is why every answer is reviewed by hand.

Limits of these numbers:

- I wrote the questions, the prompt, and the search, and some holdout questions are close variants of main-set questions. The holdout shows the fixes carry over to similar questions, not to new kinds of questions.
- Each set was run once. Answers can change between runs and that hasn't been measured.
- 43 questions find obvious mistakes. They don't support an accuracy claim.
- The main-set columns aren't strictly comparable: one trap question was replaced between v2 and v3 because the documents turned out to contain its answer.

## Run it

The documents are generated, not stored in the repo:

```bash
cd generator
pip install -r requirements.txt
python generate.py
```

Then:

```bash
cd assistant
pip install -r requirements.txt
python eval/run_retrieval_eval.py          # no API key needed
set GEMINI_API_KEY=your-key                # Windows cmd
streamlit run app.py
```

Answer evaluation:

```bash
python eval/run_answer_eval.py
python eval/run_answer_eval.py --set holdout
```

## Files

```
assistant/
├── doc_index.py          split documents, filter revisions, BM25 search
├── assistant.py          search, then ask the model
├── app.py                Streamlit chat
├── prompts/              answer prompt, v1 to v3
└── eval/
    ├── pertanyaan_dokumen.csv   main question set
    ├── pertanyaan_holdout.csv   holdout set
    ├── run_retrieval_eval.py
    ├── run_answer_eval.py
    └── hasil_*.csv              model answers with manual review
```
