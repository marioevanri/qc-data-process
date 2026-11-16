"""Run the test questions through the assistant and save the answers for review.

Every answer is saved right away, so a run that stops halfway can be resumed.

Usage (Anaconda Prompt):
    set GEMINI_API_KEY=your-key
    python eval/run_answer_eval.py
    python eval/run_answer_eval.py --set holdout
    python eval/run_answer_eval.py --prompt jawab_v2

Results go to eval/hasil_<set>_<prompt>.csv. Run the same command again to continue
after an error, or add --fresh to start that file over.
"""

import argparse
import csv
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from google import genai
from google.genai import errors

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))

from assistant import DEFAULT_MODEL, DEFAULT_PROMPT, ask, build_index  # noqa: E402

TODAY = date(2026, 7, 1)
FIELDS = ["id", "tipe", "pertanyaan", "jawaban_benar", "doc_no", "rev", "kata_kunci", "model", "prompt",
          "jawaban_model", "sumber_terambil", "cek_otomatis", "cek_manual", "catatan_review"]


def keyword_check(answer, keywords):
    # ";" separates groups that must all appear, "|" separates alternatives inside a group
    groups = [g for g in keywords.split(";") if g.strip()]
    return all(any(alt.strip().lower() in answer.lower() for alt in g.split("|")) for g in groups)


def ask_with_retry(client, index, question, model, prompt, tries=3):
    """Returns None when the run should stop and be continued later."""
    for attempt in range(1, tries + 1):
        try:
            return ask(client, index, question, model=model, prompt=prompt, today=TODAY)
        except errors.ClientError as e:
            if e.code != 429:
                raise
            # the daily free quota won't come back by waiting a minute
            if "PerDay" in str(e):
                print("\nKuota harian habis. Jalankan lagi perintah yang sama besok untuk melanjutkan.")
                return None
            print("  kena batas per menit, tunggu 60 detik...")
            time.sleep(60)
        except errors.ServerError:
            print(f"  server Gemini sibuk, tunggu 30 detik (percobaan {attempt}/{tries})...")
            time.sleep(30)
    print("\nServer Gemini masih sibuk. Coba lagi nanti dengan perintah yang sama.")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", default="dokumen", choices=["dokumen", "holdout"])
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--delay", type=float, default=7, help="seconds between questions")
    parser.add_argument("--fresh", action="store_true", help="start the result file over")
    args = parser.parse_args()

    out_file = EVAL_DIR / f"hasil_{args.set}_{args.prompt}.csv"
    with open(EVAL_DIR / f"pertanyaan_{args.set}.csv", encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    saved = []
    if out_file.exists() and not args.fresh:
        with open(out_file, encoding="utf-8-sig") as f:
            saved = list(csv.DictReader(f))
    done = {r["id"] for r in saved}

    client = genai.Client()  # reads GEMINI_API_KEY
    index = build_index()
    with open(out_file, "a" if saved else "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not saved:
            writer.writeheader()
        for q in questions:
            if q["id"] in done:
                continue
            print(f"{q['id']} {q['pertanyaan'][:70]}")
            result = ask_with_retry(client, index, q["pertanyaan"], args.model, args.prompt)
            if result is None:
                break
            answer, found = result
            row = {**q, "model": args.model, "prompt": args.prompt, "jawaban_model": answer,
                   "sumber_terambil": "; ".join(c.name for _, c in found),
                   "cek_otomatis": "OK" if keyword_check(answer, q["kata_kunci"]) else "CEK",
                   "cek_manual": "", "catatan_review": ""}
            writer.writerow(row)
            f.flush()
            saved.append(row)
            time.sleep(args.delay)

    per_type = defaultdict(lambda: [0, 0])
    for r in saved:
        per_type[r["tipe"]][1] += 1
        per_type[r["tipe"]][0] += r["cek_otomatis"] == "OK"
    print(f"\nPrompt {args.prompt}, model {args.model}, terjawab {len(saved)} dari {len(questions)}")
    for tipe, (ok, total) in per_type.items():
        print(f"  {tipe:<8} {ok} dari {total} lolos cek kata kunci")
    print(f"\nHasil di {out_file}")
    print("Cek otomatis cuma pakai kata kunci. Baca tiap jawaban dan isi kolom cek_manual.")


if __name__ == "__main__":
    main()
