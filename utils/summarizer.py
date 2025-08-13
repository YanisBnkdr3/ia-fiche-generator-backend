# utils/summarizer.py
import re
from langdetect import detect
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

# Modèle plus léger
MODEL_ID = "google/mt5-small"  # ou "t5-small" si seulement FR/EN
SENT_RE = re.compile(r'(?<=[\.\!\?])\s+')

# --- Chargement modèle/tokenizer ---
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=False)
model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL_ID,
    device_map="auto",
    low_cpu_mem_usage=True
)
summarizer_pipe = pipeline(
    "summarization",
    model=model,
    tokenizer=tokenizer,
    device=-1  # CPU
)

def smart_chunks(text: str, max_chars=1200):
    text = re.sub(r'\s+', ' ', text).strip()
    parts, buf = [], ""
    for sent in SENT_RE.split(text):
        if len(buf) + len(sent) + 1 <= max_chars:
            buf += (" " + sent)
        else:
            if buf.strip():
                parts.append(buf.strip())
            buf = sent
    if buf.strip():
        parts.append(buf.strip())
    return parts

def postprocess(summary: str, lang="fr"):
    summary = re.sub(r'\s+', ' ', summary).strip()
    sents = [s for s in SENT_RE.split(summary) if len(s.strip()) >= 20]
    if lang == "fr":
        sents = [s for s in sents if not re.search(r'\b(the|and|is|was)\b', s, re.I)]
    return " ".join(sents)

def summarize_text(text: str, max_length=120, min_length=40):
    if not text or not text.strip():
        return ""
    try:
        lang = detect(text[:1000])
    except Exception:
        lang = "fr"

    chunks = smart_chunks(text, max_chars=1200)
    outs = []
    for ch in chunks:
        try:
            out = summarizer_pipe(
                ch,
                max_length=max_length,
                min_length=min_length,
                do_sample=False
            )[0]["summary_text"]
        except Exception:
            out = ""
        if out:
            outs.append(out)

    merged = " ".join(outs)
    return postprocess(merged, lang=lang or "fr")
