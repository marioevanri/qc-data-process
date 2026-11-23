import os

import streamlit as st
from google import genai
from google.genai import errors

from assistant import DEFAULT_MODEL, ask, build_index

MAX_QUESTIONS = 15
EXAMPLES = [
    "Komplain CMP-25-010 dari batch mana dan bagaimana hasil QC batch itu?",
    "Batch 25062434P1 statusnya apa dan kenapa?",
    "Lot PO-250623-01 dipakai di batch mana saja dan apakah ada masalah sensory?",
    "Seberapa sering hasil verifikator beda dengan KimFis di Februari 2026?",
    "Berapa batas kadar air NDC-28P yang berlaku sekarang?",
]

st.set_page_config(page_title="QC Assistant", page_icon="🧪")


@st.cache_resource
def get_index():
    return build_index()


@st.cache_resource
def get_client(key):
    return genai.Client(api_key=key)


def secret(name, default=""):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except Exception:  # no secrets.toml on this machine
        return os.environ.get(name, default)


st.title("QC Assistant")
st.caption("Tanya SOP, spesifikasi, NCR, memo, dan laporan komplain, atau sebut nomor komplain, batch, atau lot "
           "bahan baku untuk melihat datanya. PT Sari Krimer Nusantara adalah pabrik fiktif.")
st.info("Semua data dan dokumen di demo ini fiktif. Jawaban bisa salah, jadi cocokkan dengan data dan kutipan "
        "di bawah tiap jawaban. Data diambil lewat query yang sudah diuji, modelnya tidak menulis SQL sendiri. "
        "Jangan masukkan data rahasia, karena pertanyaan dikirim ke Gemini API versi gratis.")

api_key = secret("GEMINI_API_KEY")
if not api_key:
    st.error("GEMINI_API_KEY belum diisi. Taruh di .streamlit/secrets.toml atau set sebagai environment variable.")
    st.stop()

index = get_index()
client = get_client(api_key)
model = secret("GEMINI_MODEL", DEFAULT_MODEL)

if "messages" not in st.session_state:
    st.session_state.messages = []


def show_data(data):
    with st.expander(f"Data database ({len(data)} query)"):
        for d in data:
            st.markdown(f"**{d['title']}**")
            st.text(d["text"])


def show_sources(sources):
    with st.expander(f"Sumber ({len(sources)} kutipan)"):
        for s in sources:
            st.markdown(f"**{s['label']}**  \n`{s['file']}`")
            st.text(s["text"])


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("data"):
            show_data(m["data"])
        if m.get("sources"):
            show_sources(m["sources"])

asked = sum(m["role"] == "user" for m in st.session_state.messages)
question = st.chat_input("Tulis pertanyaan", disabled=asked >= MAX_QUESTIONS)

if not st.session_state.messages:
    st.write("Contoh pertanyaan:")
    for example in EXAMPLES:
        if st.button(example):
            question = example

if asked >= MAX_QUESTIONS:
    st.warning(f"Batas {MAX_QUESTIONS} pertanyaan per sesi sudah tercapai. Muat ulang halaman untuk mulai lagi.")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            # every question is searched on its own, earlier messages are not sent to the model
            with st.spinner("Mencari di database dan dokumen..."):
                answer, found, results = ask(client, index, question, model=model)
            sources = [{"label": c.label, "file": c.file, "text": c.text} for _, c in found]
            data = [{"title": title, "text": r["text"]} for title, r in results]
        except errors.ClientError as e:
            answer, sources, data = ("Kuota Gemini gratis sedang habis, coba lagi beberapa saat."
                                     if e.code == 429 else f"Permintaan ditolak Gemini ({e.code})."), [], []
        except errors.APIError:
            answer, sources, data = "Server Gemini sedang sibuk, coba lagi sebentar.", [], []
        st.markdown(answer)
        if data:
            show_data(data)
        if sources:
            show_sources(sources)
    st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources, "data": data})
    st.rerun()
