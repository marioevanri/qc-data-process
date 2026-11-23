# QC Assistant (work in progress)

A chat assistant for QC staff of a fictional creamer and milk powder plant. It answers from about 180 QC documents (SOPs, product specs, NCRs, memos, shift logbooks, meeting notes, complaint investigations) and from the cleaned QC database built by `../pipeline`. Every answer names the documents and the data it came from.

Database questions go through a small set of tested queries, not through SQL written by the model. Four kinds are covered so far: tracing a complaint, the status of a batch, where a raw material lot went, and how often the sensory verifikator agrees with the KimFis analysts.

> Everything here is fictional. The documents come from the synthetic data generator in `../generator`.

## How it works

1. **Split.** Each document is cut into sections (359 chunks from 182 documents), and the document title is added to every chunk.
2. **Filter revisions.** SOPs and specs exist in several revisions. The code reads the period a question is about ("Februari 2026", "15 November 2025", or no date, meaning today) and drops revisions that weren't in force then. This is plain code, not the model.
3. **Search.** BM25 keyword search with a rough Indonesian stemmer. No embeddings, no vector database. Rules (SOP, spec) and records (NCR, memo, logbook, ...) are ranked separately and the top 3 of each are kept, because records outnumber rules ten to one and would otherwise push the rule out of the results.
4. **Data.** If the question names a complaint (`CMP-25-010`), a batch (`25062434P1`) or a lot (`PO-250623-01`), or compares the verifikator with KimFis, the matching query in `queries.py` runs and returns a short summary. Documents that mention that number word for word are added to the chunks, so a complaint brings its investigation report. The rule the data is judged against is searched separately (the release SOP and the grade's spec for a batch), using the revision that was valid on the batch's production date rather than today's.
5. **Answer.** Gemini writes the answer from the data summary and the chunks only, cites them, and says "Tidak ditemukan di dokumen" when the answer isn't there.

### The queries

| Function | Question it answers | Tables |
|---|---|---|
| `trace_complaint` | which batch and delivery, who else got that batch, what QC found on it | complaints, shipments, plus everything in `batch_status` |
| `batch_status` | lab results against the spec revision valid on the production date, sensory, micro, raw material lots used, last release status per mix (with the release before a recall), deliveries, complaints | production, qc_lab_final, sensory, verifikator, micro, rm_receiving, release_history, shipments, complaints, spec_limits |
| `lot_usage` | incoming decision and test results, the mixes and batches it went into, off-flavor rate against mixes without flagged lots, release decisions, complaints | rm_receiving, production, sensory, release_history, complaints |
| `verifikator_agreement` | agreement on exact result, on class and on accept/reject, per verifikator, analyst and grade, and which samples get verified | sensory_verifikator, sensory_kimfis |

Fixed queries instead of text-to-SQL, because a QC answer has rules that are easy to get wrong in a free query: the spec revision depends on the production date, a retest replaces only the parameters it re-measured, and a mix-level join is needed to tie a lot to sensory results. Those rules are written and tested once here.

The verifikator numbers carry a warning on purpose. Every TP3 from KimFis is re-checked but only about a quarter of the Pass samples are, so the agreement rate describes the verified samples, not all samples.

Every query result opens with an `Inti` line: the few facts an answer can't leave out, with every percentage next to its count ("27 dari 28 (96,4%)"). For a lot, the TP3 rate with the lot and the rate in the comparison group sit in the same sentence. A PERINGATAN line is added when there are fewer than 5 TP3 or fewer than 30 comparison samples, and when some of the lot's mixes also used another Conditional lot. The thresholds are rules of thumb, not a test. There is no p-value on purpose: samples from one mix aren't independent, so a test over samples would look far more certain than it is.

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

Database questions, also reviewed by hand:

| Set | Prompt v4 | Prompt v5 |
|---|---|---|
| Main (11 questions) | 5 correct, 5 partly, 1 wrong | 8 correct, 3 partly |
| Q12, added after the v4 run | not run | correct |
| Holdout (7 questions) | not run | 3 correct, 4 partly |

The v5 changes were designed from the 11 main-set answers, so the main-set score flatters it. The holdout was written before v5 was run and is the score to go by. The gap between the two is what tuning on the test questions looks like, but 7 questions are too few to tell how much of it is tuning and how much is that the holdout asks for more judgment (does this lot affect sensory, why was this recalled).

Before changing anything after v5, the holdout was run twice more with the same code and prompt: once more with flash-lite, and once with `gemini-3.6-flash`.

| Holdout, prompt v5 | Correct | Partly | Wrong |
|---|---|---|---|
| flash-lite, run 1 | 3 | 4 | 0 |
| flash-lite, run 2 | 3 | 3 | 1 |
| gemini-3.6-flash | 6 | 0 | 1 |

The two flash-lite runs got the same count but disagreed on 3 of 7 questions. With one run per version, a difference of one or two questions between prompt versions is noise. Flash kept the lines flash-lite dropped (the comparison group, the urgent release before a recall, the sample count), so most of the omissions are a limit of the smaller model. But the second flash-lite run and Flash both said a lot with 1 mixgrade TP3 in 63 samples affects sensory. Judging weak evidence failed on both models, which is why that judgment now sits in the query as a PERINGATAN line instead of being left to the model.

The v6 changes (the `Inti` line, counts next to percentages, prompt v6) were designed from the v5 holdout answers, so that holdout is now a development set too. Holdout 2 was written before v6 was run:

| Holdout 2, prompt v6 | Correct | Partly | Wrong |
|---|---|---|---|
| flash-lite, run 1 | 5 | 3 | 1 |
| flash-lite, run 2 | 7 | 2 | 0 |
| gemini-3.6-flash, 7 of 9 answered | 6 | 0 | 1 |

Holdout 2 has other questions than the first holdout, so these numbers can't be set against the v5 ones as a controlled comparison. What they show:

- The gap between flash-lite and Flash is smaller than with v5 (6 and 7 of 9 against 3 of 7). Putting the facts in one fixed line seems to help the smaller model most. Flash-lite still drops lines the prompt makes mandatory (a CATATAN, a PERINGATAN) in some runs, Flash didn't.
- No run got D06 right, and that one is my fault, not the model's. The `Inti` line gave the mixed comparison first (5 TP3 in 63 samples against 0 in 36), and the clean one, for mixes without the other bad lot (1 in 45), came on a PERINGATAN line below it. Flash quoted both lines and still opened with "Ada indikasi". The number that leads has to be the one that holds. This was fixed after the holdout 2 run, so the fix hasn't been tested on unseen questions.

The assistant stops here, at prompt v6. What's left is flash-lite sometimes dropping lines the prompt makes mandatory, which is a limit of the model, and every further round would need another holdout.

What went wrong along the way, and what it changed:

- With one shared ranking, "moisture limit of NDC-28P" retrieved complaint reports instead of the spec. That led to ranking rules and records separately.
- Without the stemmer, a question using "berganti" missed the memo that says "menggantikan".
- Prompt v2 answered "yes, allowed" to a question whose own quoted rule said the opposite. Prompt v3 makes the model write the rule first and the conclusion after. The keyword check had marked that wrong answer as OK, which is why every answer is reviewed by hand.
- With the database connected (v4), the numbers were right but the model dropped what qualifies them: the warning that verified samples aren't random, the reason a lot was never used, the batch number the query suggested for a typo. It also subtracted 74.8 % from 100 % on its own and called the person who signed off a release "the verifikator". The query text now states the difference directly, puts warnings on a line starting with PERINGATAN and names who decided, and prompt v5 requires those lines to be carried into the answer.
- For a batch question, the search first returned specs for other grades and today's SOP revision. The release SOP and the grade's spec are now searched separately, at the revision valid on the production date.
- The number formatter stripped trailing zeros from whole numbers too, so TPC 380 went to the model as 38 and coliform 20 as 2. That hit most micro results (1915 of 2227 values end in zero). The v4 review didn't catch it because none of the checked facts were micro counts. It showed up while writing the holdout, when one summary said coliform 2 on one line and coliform 20 on another.
- Prompt v5 fixed what it named: the PERINGATAN line, who decided a release, the suggested batch number. Lines it didn't name were still dropped. One answer says a lot "caused" off-flavor without the comparison group (51 % against 3.3 %), another gives 96.4 % agreement without saying it comes from 28 samples, a third explains a recall without the urgent release that let the mix leave before the micro result. When the data was weak (1 TP3 in 63 samples) the model listed the numbers and never answered the question. Naming more lines in the prompt would fix these and miss the next ones.
- In the v4 review I let a missing comparison group pass on Q07. I kept that grading in v5 so the two runs compare, so the main-set score is lenient on that point.
- Prompt v5 told the model to write numbers "with their units". The query text has no units, so the model made some up, one of them wrong (a viscosity spec in %). Prompt v6 only allows units that are in the data or the documents.
- Two facts in the first holdout were never checked: an unquoted decimal comma ("1,6%") split the CSV field. `run_data_eval.py` now stops on a row with too many columns.
- While writing holdout 2, a lot looked guilty of oxidised off-flavor (5 TP3 in 63 samples) until it turned out 6 of its 21 mixes also used the bad palm oil lot from the same week. Without those mixes it had 1 TP3 in 45 samples. The comparison group had always been cleaned of other flagged lots, the group with the lot hadn't.
- When no revision of an SOP was in force on the production date, the search silently fell back to the first revision, so a January batch was judged by a rule from March. The data now gets a CATATAN line when that happens.

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

Database questions need the database first (`python ../pipeline/build_db.py`). Routing and query results can be checked without an API key, the answers with one:

```bash
python eval/run_data_eval.py
python eval/run_data_eval.py --set data_holdout2
python eval/run_answer_eval.py --set data
python eval/run_answer_eval.py --set data_holdout2
```

`run_data_eval.py` currently passes 12 of 12, 7 of 7 on the first holdout and 9 of 9 on holdout 2: every question reaches the right query and the facts it needs are in the result. Query bugs found while writing a holdout were fixed before any model answer to it was seen, so a holdout tests the prompt and the model, not the queries. `--model` and `--tag` on `run_answer_eval.py` add to the result file name, so a reviewed file is never overwritten.

## Files

```
assistant/
├── doc_index.py          split documents, filter revisions, BM25 search
├── queries.py            the database queries
├── assistant.py          route the question, run queries, search, then ask the model
├── app.py                Streamlit chat
├── prompts/              answer prompt, v1 to v6 (v4 adds the database part)
└── eval/
    ├── pertanyaan_dokumen.csv   main question set
    ├── pertanyaan_holdout.csv   holdout set
    ├── pertanyaan_data.csv      database questions, with the expected route and facts
    ├── pertanyaan_data_holdout.csv   database questions written before prompt v5 was run
    ├── pertanyaan_data_holdout2.csv  database questions written before prompt v6 was run
    ├── run_retrieval_eval.py
    ├── run_data_eval.py         routing and query check, no model
    ├── run_answer_eval.py
    └── hasil_*.csv              model answers with manual review
```
