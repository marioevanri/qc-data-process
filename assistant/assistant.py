"""Answer a QC question from the documents: search first, then let the model write the answer.

The model only sees the chunks the search returned, and has to cite them by document name.
"""

from datetime import date
from pathlib import Path

from google import genai
from google.genai import types

from doc_index import Index, load_chunks

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_PROMPT = "jawab_v3"


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


def ask(client, index, question, model=DEFAULT_MODEL, prompt=DEFAULT_PROMPT, today=None):
    """Returns the answer and the chunks it was based on."""
    today = today or date.today()
    found = index.search(question, today=today)
    if not found:
        return "Tidak ditemukan di dokumen.", []
    template = (BASE_DIR / "prompts" / f"{prompt}.md").read_text(encoding="utf-8")
    system = template.replace("{hari_ini}", f"{today:%d/%m/%Y}").replace("{kutipan}", format_sources(found))
    response = client.models.generate_content(
        model=model, contents=question,
        config=types.GenerateContentConfig(system_instruction=system))
    return (response.text or "").strip(), found


if __name__ == "__main__":
    # quick test from the terminal: python assistant.py "pertanyaan"
    import sys

    client = genai.Client()  # reads GEMINI_API_KEY
    answer, found = ask(client, build_index(), " ".join(sys.argv[1:]))
    print(answer, "\n")
    for _, c in found:
        print(f"- {c.label}  ({c.file})")
