"""Load the QC documents, split them into sections, and search them with BM25.

Plain keyword search, no embeddings and no extra packages. SOPs and specs come in
several revisions, so before searching we keep only the revisions that were valid
for the period the question is about.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "generator" / "docs"

MONTHS = ["januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus",
          "september", "oktober", "november", "desember"]

# words too common to help the search
STOPWORDS = set("""yang dan di ke dari untuk pada dengan atau itu ini adalah apa berapa bagaimana
kapan kenapa mengapa siapa mana apakah saja saat oleh sebagai juga akan sudah belum tidak bisa
harus boleh kalau jika maka karena lalu setelah sebelum sampai dalam luar per tiap setiap
nya the of""".split())

RULES = {"sop", "spec"}  # controlled documents, everything else is a record of what happened
MAX_CHUNK = 1200  # characters, small sections are merged up to about this size


@dataclass
class Chunk:
    file: str
    doc_type: str          # folder name: sop, spec, ncr, memo, complaints, logbook, meetings
    doc_no: str            # SOP-QC-005, NCR-25-003, ...
    rev: str               # "" for documents without revisions
    valid_from: date | None
    doc_date: date | None
    title: str
    section: str
    text: str

    @property
    def name(self):
        return f"{self.doc_no} Rev {self.rev}" if self.rev else self.doc_no

    @property
    def label(self):
        return f"{self.name}, {self.section}" if self.section else self.name


def parse_date(text):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text or "")
    return date(int(m[3]), int(m[2]), int(m[1])) if m else None


def read_header(text):
    """The small 'key | value' table under the title of every document."""
    meta = {}
    for line in text.split("\n## ")[0].splitlines():
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", line)
        if m and not set(m[1]) <= set("-: "):
            meta[m[1]] = m[2]
    return meta


def split_sections(body):
    """Split on ## and ### headings, then merge small neighbours so a chunk has some context."""
    parts = re.split(r"\n(?=#{2,3} )", body)
    chunks, current, heading = [], "", ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        first = part.splitlines()[0]
        name = first.lstrip("# ").strip() if first.startswith("#") else ""
        if current and len(current) + len(part) > MAX_CHUNK:
            chunks.append((heading, current))
            current, heading = "", ""
        if not current:
            heading = name
        current = f"{current}\n\n{part}".strip()
    if current:
        chunks.append((heading, current))
    return chunks


def load_chunks(docs_dir=DOCS_DIR):
    chunks = []
    for path in sorted(Path(docs_dir).rglob("*.md")):
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        title = text.splitlines()[0].lstrip("# ").strip()
        meta = read_header(text)
        doc_no = (meta.get("No. Dokumen") or meta.get("No. NCR") or meta.get("No. Memo")
                  or path.stem.removeprefix("INV-"))
        doc_date = parse_date(meta.get("Tanggal Berlaku") or meta.get("Tanggal") or meta.get("Tanggal terima")
                              or meta.get("Tanggal rapat"))
        rev = meta.get("Revisi", "")
        for section, body in split_sections(text):
            chunks.append(Chunk(
                file=path.relative_to(docs_dir).as_posix(), doc_type=path.parent.name, doc_no=doc_no, rev=rev,
                valid_from=doc_date if rev else None, doc_date=doc_date, title=title, section=section,
                # the title goes into every chunk so a section still knows which document it belongs to
                text=body if body.startswith("# ") else f"{title}\n\n{body}"))
    return chunks


# which period is the question about

def question_period(question, today=None):
    """(start, end) of the period a question refers to. Without a date it means today."""
    today = today or date.today()
    q = question.lower()
    d = parse_date(q)
    if d:
        return d, d
    month_names = "|".join(MONTHS)
    m = re.search(rf"(?:(\d{{1,2}})\s+)?({month_names})\s+(20\d{{2}})", q)
    if m:
        year, month = int(m[3]), MONTHS.index(m[2]) + 1
        if m[1]:
            d = date(year, month, int(m[1]))
            return d, d
        next_month = date(year + month // 12, month % 12 + 1, 1)
        return date(year, month, 1), next_month - timedelta(days=1)
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        return date(int(m[1]), 1, 1), date(int(m[1]), 12, 31)
    return today, today


def valid_revisions(chunks, question, today=None):
    """Drop revisions that were not in force during the period the question is about."""
    # a question that names a revision wants to see that revision, so don't filter
    if re.search(r"\brev(?:isi)?\.?\s*[0-9a-z]{1,2}\b", question.lower()):
        return chunks
    start, end = question_period(question, today)
    starts = {}
    for c in chunks:
        if c.rev:
            starts.setdefault(c.doc_no, set()).add((c.valid_from or date.min, c.rev))
    keep = set()
    for doc_no, revisions in starts.items():
        ordered = sorted(revisions)
        for i, (valid_from, rev) in enumerate(ordered):
            valid_until = ordered[i + 1][0] - timedelta(days=1) if i + 1 < len(ordered) else date.max
            if valid_from <= end and valid_until >= start:
                keep.add((doc_no, rev))
        if not any(d == doc_no for d, _ in keep):
            keep.add((doc_no, ordered[0][1]))  # question is about a time before the first revision
    return [c for c in chunks if not c.rev or (c.doc_no, c.rev) in keep]


# BM25

USE_STEMMER = True
PREFIXES = ("meng", "meny", "mem", "men", "me", "peng", "pem", "pen", "per", "pe", "ber", "ter", "di", "ke", "se")
SUFFIXES = ("kan", "nya", "lah", "kah", "an")


def stem(word):
    """Rough Indonesian stemmer, so "berganti" and "menggantikan" both become "ganti".

    It doesn't need to return real root words. It only has to cut the question and the
    documents the same way.
    """
    if not word.isalpha() or len(word) < 6:
        return word
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[:-len(suffix)]
            break
    for _ in range(2):  # "diperpanjang" has two prefixes
        for prefix in PREFIXES:
            if word.startswith(prefix) and len(word) - len(prefix) >= 4:
                word = word[len(prefix):]
                break
    return word


def tokenize(text):
    tokens = []
    for word in re.findall(r"[a-z0-9]+(?:[-.,/][a-z0-9]+)*", text.lower()):
        if word in STOPWORDS:
            continue
        if USE_STEMMER:
            word = stem(word)
        tokens.append(word)
        # "ndc-28p" should also match "ndc" and "28p", "sop-qc-005" also "005"
        parts = re.split(r"[-/]", word)
        if len(parts) > 1:
            tokens += [p for p in parts if p and p not in STOPWORDS]
    return tokens


class Index:
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.counts = [Counter(tokenize(c.text)) for c in chunks]
        self.lengths = [sum(c.values()) for c in self.counts]
        self.avg_len = sum(self.lengths) / len(chunks)
        doc_freq = Counter(t for c in self.counts for t in c)
        self.idf = {t: math.log(1 + (len(chunks) - n + 0.5) / (n + 0.5)) for t, n in doc_freq.items()}

    def score(self, i, terms):
        total = 0.0
        for t in terms:
            tf = self.counts[i].get(t, 0)
            if tf:
                norm = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_len)
                total += self.idf[t] * tf * (self.k1 + 1) / norm
        return total

    def containing(self, text, limit=4):
        """Chunks that mention a number word for word, like a complaint or batch number.
        BM25 splits 'CMP-25-005' into pieces that also match every other 2025 document."""
        text = text.lower()
        return [(0.0, c) for c in self.chunks if text in c.text.lower()][:limit]

    def search(self, question, k_rules=3, k_records=3, today=None, period_from=None):
        """Best chunks from the rules (SOP, spec) and from the records (NCR, memo, logbook, ...).

        The two groups are ranked separately. There are ten times more record chunks than
        rule chunks, so in one shared ranking a complaint that mentions "kadar air NDC-28P"
        pushes the spec that defines the limit out of the list.

        period_from: text to read the period from when it isn't the search text itself, for
        example a fixed search for an SOP made on behalf of a question about 2025.
        """
        allowed = {id(c) for c in valid_revisions(self.chunks, period_from or question, today)}
        terms = tokenize(question)
        scored = [(self.score(i, terms), c) for i, c in enumerate(self.chunks) if id(c) in allowed]
        scored = sorted(((s, c) for s, c in scored if s > 0), key=lambda x: -x[0])
        rules = [x for x in scored if x[1].doc_type in RULES][:k_rules]
        records = [x for x in scored if x[1].doc_type not in RULES][:k_records]
        return rules + records
