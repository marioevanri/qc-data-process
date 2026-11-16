import os

import streamlit as st
from google import genai
from google.genai import errors

from assistant import DEFAULT_MODEL, ask, build_index

MAX_QUESTIONS = 15
EXAMPLES = [
    "Berapa batas kadar air NDC-28P yang berlaku sekarang?",
    "Februari 2026, berapa persen sampel yang diverifikasi acak?",
    "Apa yang harus dilakukan setelah lampu NIRS diganti?",
    "Apakah CRM-RT boleh release urgent pada Oktober 2025?",
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
st.caption("Tanya SOP, spesifikasi, NCR, memo, logbook, notulen, dan laporan investigasi komplain "
           "PT Sari Krimer Nusantara (pabrik fiktif).")
st.info("Semua dokumen di demo ini fiktif. Jawaban bisa salah, jadi cocokkan dengan kutipan sumber di bawah tiap "
        "jawaban. Asisten ini baru membaca dokumen, belum tersambung ke database hasil analisa. "
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


def show_sources(sources):
    with st.expander(f"Sumber ({len(sources)} kutipan)"):
        for s in sources:
            st.markdown(f"**{s['label']}**  \n`{s['file']}`")
            st.text(s["text"])


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
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
            with st.spinner("Mencari di dokumen..."):
                answer, found = ask(client, index, question, model=model)
            sources = [{"label": c.label, "file": c.file, "text": c.text} for _, c in found]
        except errors.ClientError as e:
            answer, sources = ("Kuota Gemini gratis sedang habis, coba lagi beberapa saat."
                               if e.code == 429 else f"Permintaan ditolak Gemini ({e.code})."), []
        except errors.APIError:
            answer, sources = "Server Gemini sedang sibuk, coba lagi sebentar.", []
        st.markdown(answer)
        if sources:
            show_sources(sources)
    st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources})
    st.rerun()
