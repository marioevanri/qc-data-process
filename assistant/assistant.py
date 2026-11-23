"""Answer a QC question from the database and the documents, then let the model write the answer.

The question is read for a complaint number, a batch, a raw material lot or a question about
the verifikator. Each of those runs a fixed query (queries.py). The documents are searched as
before. The model only sees the query results and the chunks, and has to cite them.
"""

import re
from datetime import date
from pathlib import Path

from google import genai
from google.genai import types

import queries
from doc_index import Index, load_chunks, question_period

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_PROMPT = "jawab_v6"

COMPLAINT = re.compile(r"\bCMP-\d{2}-\d{3}\b", re.IGNORECASE)
# the date part is sometimes typed with the letter O or I ('25O31434P1'), like in the sheets
BATCH = re.compile(r"\b[\dOI]{8}(?:P1|P2|RT)\b", re.IGNORECASE)
LOT = re.compile(r"\b(HCO|PO|GSS|CAS|SMP)-?(\d{6})-?(\d{1,2})\b", re.IGNORECASE)
# a question about how verifikator and KimFis compare, not about the verification rules in the SOP
VERIFIKATOR = re.compile(r"verifikator", re.IGNORECASE)
COMPARE = re.compile(r"kimfis|beda|sama|sepakat|setuju|sesuai|cocok|konsisten", re.IGNORECASE)
NO_DATE = date(1900, 1, 1)
# the rule each kind of database question is judged against. Searched on its own, because the
# question ("batch X statusnya apa?") rarely has the words that find the SOP.
RULE_TOPICS = {
    "batch": "status produk hold release reject disposisi",
    "lot": "penerimaan bahan baku conditional reject",
    "verifikator": "verifikasi sensory verifikator",
}


def build_index():
    return Index(load_chunks())


def format_sources(found):
    blocks = []
    for _, c in found:
        if c.rev:
            when = f"berlaku sejak {c.valid_from:%d/%m/%Y}" if c.valid_from else ""
        else:
            when = f"tanggal {c.doc_date:%d/%m/%Y}" if c.doc_date else ""
        details = ", ".join(x for x in (f"bagian {c.section}" if c.section else "", c.doc_type, when) if x)
        blocks.append(f"Sumber: {c.name} ({details})\n{c.text}")
    return "\n\n---\n\n".join(blocks)


def grade_in(question):
    """'NDC-28P', 'ndc 28p' or 'NDC28P' in the question, checked against the grades in the database."""
    squashed = re.sub(r"[^A-Z0-9]", "", question.upper())
    grades = queries.read("SELECT DISTINCT grade FROM spec_limits")["grade"]
    return next((g for g in grades if re.sub(r"[^A-Z0-9]", "", g) in squashed), None)


def produced(result):
    """Grade and production date (dd/mm/yyyy) of the batch in a batch or complaint result."""
    production = result.get("data", {}).get("produksi")
    if production is None or production.empty:
        return "", ""
    day = production["prod_date"].iloc[0]
    return production["grade"].iloc[0], f"{day[8:10]}/{day[5:7]}/{day[:4]}"


def rule_searches(results, question):
    """Searches that bring the SOP and spec each database result should be judged against, as
    (search text, text to read the period from). A batch is judged by the revision that was
    valid on its production date, not today's."""
    searches = []
    for title, r in results:
        if title.startswith(("Batch", "Komplain")):
            grade, made = produced(r)
            period = made or question
            searches.append((RULE_TOPICS["batch"], period))
            if grade:
                searches.append((f"spesifikasi release {grade}", period))
        elif title.startswith("Lot"):
            searches.append((RULE_TOPICS["lot"], question))
        elif title.startswith("Verifikator"):
            searches.append((RULE_TOPICS["verifikator"], question))
    return list(dict.fromkeys(searches))


def rule_notes(found, period, question):
    """When no revision was in force on the production date, the search falls back to the
    first one there is. Say so, otherwise a batch from January gets judged by a rule from March."""
    if period == question:
        return []
    made = question_period(period)[0]
    return [f"CATATAN: {c.name} baru berlaku {c.valid_from:%d/%m/%Y}, sesudah batch diproduksi {made:%d/%m/%Y}. "
            f"Di dokumen tidak ada revisi yang berlaku saat batch dibuat, jadi aturan ini belum tentu berlaku untuk batch ini."
            for _, c in found if c.rev and c.valid_from and c.valid_from > made]


def batch_number(typed):
    typed = typed.upper()
    return typed[:8].replace("O", "0").replace("I", "1") + typed[8:]


def find_data(question, today=None):
    """Run the queries the question asks for. Returns a list of (title, result) and the
    numbers found, so the documents that mention them can be added too. Without the database
    (pipeline/build_db.py not run yet) the assistant answers from the documents only."""
    results, numbers = [], []
    if not queries.DB_PATH.exists():
        return results, numbers
    for found in dict.fromkeys(m.upper() for m in COMPLAINT.findall(question)):
        results.append((f"Komplain {found}", queries.trace_complaint(found)))
        numbers.append(found)
    for found in dict.fromkeys(f"{a.upper()}-{b}-{int(c):02d}" for a, b, c in LOT.findall(question)):
        results.append((f"Lot {found}", queries.lot_usage(found)))
        numbers.append(found)
    # a batch inside a complaint trace is already covered there
    if not results:
        for found in dict.fromkeys(batch_number(m) for m in BATCH.findall(question)):
            results.append((f"Batch {found}", queries.batch_status(found)))
            numbers.append(found)
    if VERIFIKATOR.search(question) and COMPARE.search(question) and not results:
        start, end = question_period(question, today=NO_DATE)
        start, end = (None, None) if start == NO_DATE else (start, end)
        results.append(("Verifikator vs KimFis", queries.verifikator_agreement(start, end, grade_in(question))))
    return results[:3], numbers


def format_data(results):
    if not results:
        return "(tidak ada data database untuk pertanyaan ini)"
    return "\n\n---\n\n".join(f"{title}\n{r['text']}" for title, r in results)


def ask(client, index, question, model=DEFAULT_MODEL, prompt=DEFAULT_PROMPT, today=None, use_data=True):
    """Returns the answer, the chunks it was based on and the database results."""
    today = today or date.today()
    results, numbers = find_data(question, today) if use_data else ([], [])
    # documents that mention the complaint, batch or lot word for word come first, then the
    # rules the data is judged against, then the normal search
    by_number = [x for n in numbers for x in index.containing(n)]
    searches = rule_searches(results, question)
    rules, notes = [], []
    for text, period in searches:
        found_rules = index.search(text, k_rules=1, k_records=0, today=today, period_from=period)
        rules += found_rules
        notes += rule_notes(found_rules, period, question)
    notes = list(dict.fromkeys(notes))
    # a question about a batch without a date of its own is about the batch's production date,
    # so older revisions apply to the normal search too
    period = None
    if question_period(question, today=NO_DATE)[0] == NO_DATE:
        period = next((p for _, p in searches if p != question), None)
    found, seen = [], set()
    for score, chunk in by_number + rules + index.search(question, today=today, period_from=period):
        if id(chunk) not in seen:
            seen.add(id(chunk))
            found.append((score, chunk))
    if not found and not results:
        return "Tidak ditemukan di dokumen.", [], []
    template = (BASE_DIR / "prompts" / f"{prompt}.md").read_text(encoding="utf-8")
    system = (template.replace("{hari_ini}", f"{today:%d/%m/%Y}").replace("{kutipan}", format_sources(found))
              .replace("{data}", "\n\n".join([format_data(results)] + notes)))
    response = client.models.generate_content(
        model=model, contents=question,
        config=types.GenerateContentConfig(system_instruction=system))
    return (response.text or "").strip(), found, results


if __name__ == "__main__":
    # quick test from the terminal: python assistant.py "pertanyaan"
    import sys

    client = genai.Client()  # reads GEMINI_API_KEY
    answer, found, results = ask(client, build_index(), " ".join(sys.argv[1:]))
    print(answer, "\n")
    for title, _ in results:
        print(f"- database: {title}")
    for _, c in found:
        print(f"- {c.label}  ({c.file})")
