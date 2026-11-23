"""Check the database side of the assistant without calling Gemini.

For every question in pertanyaan_data.csv (or the holdout): did the question go to the right
query (rute), and does the query result contain the facts it should (fakta, separated by ';')?
This tests the routing and the queries, so a wrong answer later can be blamed on the right part.

Usage:
    python eval/run_data_eval.py
    python eval/run_data_eval.py --set data_holdout
"""

import argparse
import csv
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))

from assistant import find_data  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", default="data", choices=["data", "data_holdout", "data_holdout2"])
    args = parser.parse_args()
    with open(EVAL_DIR / f"pertanyaan_{args.set}.csv", encoding="utf-8") as f:
        questions = list(csv.DictReader(f))
    # an unquoted comma ('1,6%') splits a field and the rest of the facts silently drop out
    broken = [q["id"] for q in questions if None in q]
    if broken:
        sys.exit(f"Baris {', '.join(broken)} punya kolom lebih. Kolom yang berisi koma harus diberi tanda kutip.")
    passed = 0
    for q in questions:
        results, _ = find_data(q["pertanyaan"])
        routes = [title for title, _ in results]
        text = "\n".join(r["text"] for _, r in results)
        route_ok = routes == [q["rute"]] if q["rute"] else not routes
        missing = [fact for fact in q["fakta"].split(";") if fact and fact not in text]
        ok = route_ok and not missing
        passed += ok
        print(f"{q['id']} {'OK ' if ok else 'CEK'} {q['pertanyaan'][:70]}")
        if not route_ok:
            print(f"     rute: {routes or 'tidak ada'}, seharusnya {q['rute'] or 'tidak ada'}")
        if missing:
            print(f"     fakta tidak ada di hasil query: {'; '.join(missing)}")
    print(f"\n{passed} dari {len(questions)} lolos")


if __name__ == "__main__":
    main()
