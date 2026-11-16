"""Check whether the search finds the right document for each test question.

No language model involved, this only scores the retrieval step.

Usage:
    python eval/run_retrieval_eval.py
    python eval/run_retrieval_eval.py --set holdout
"""

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))

from doc_index import Index, load_chunks  # noqa: E402

# "sekarang" in a question means this date, so results don't change from day to day
TODAY = date(2026, 7, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", default="dokumen", choices=["dokumen", "holdout"])
    args = parser.parse_args()

    index = Index(load_chunks())
    with open(EVAL_DIR / f"pertanyaan_{args.set}.csv", encoding="utf-8") as f:
        # trap questions have no source document, so there is nothing to find
        questions = [q for q in csv.DictReader(f) if q["doc_no"]]

    hits, first = {}, {}
    for q in questions:
        found = index.search(q["pertanyaan"], today=TODAY)
        wanted = q["doc_no"].split("|")
        right = [c for _, c in found if c.doc_no in wanted and (not q["rev"] or c.rev == q["rev"])]
        # position inside its own group, rules and records are ranked separately
        group = [c for _, c in found if right and (c.doc_type in ("sop", "spec")) == (right[0].doc_type in ("sop", "spec"))]
        rank = group.index(right[0]) + 1 if right else None
        wrong_rev = [c.label for _, c in found if q["rev"] and c.doc_no in wanted and c.rev != q["rev"]]
        hits[q["tipe"]] = hits.get(q["tipe"], 0) + (rank is not None)
        first[q["tipe"]] = first.get(q["tipe"], 0) + (rank == 1)
        note = f"  revisi lain ikut terambil: {wrong_rev[0]}" if wrong_rev else ""
        print(f"{q['id']}  {'peringkat ' + str(rank) if rank else 'TIDAK KETEMU':<13} {q['pertanyaan'][:70]}{note}")
        if rank is None:
            print("     yang terambil:", "; ".join(c.label for _, c in found))

    print()
    for tipe in hits:
        total = sum(q["tipe"] == tipe for q in questions)
        print(f"{tipe:<8} dokumen yang benar terambil {hits[tipe]} dari {total}, di peringkat 1: {first[tipe]}")


if __name__ == "__main__":
    main()
