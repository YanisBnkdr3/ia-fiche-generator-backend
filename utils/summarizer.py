# utils/summarizer.py
import re
from langdetect import detect
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

MODEL_ID = "csebuetnlp/mT5_multilingual_XLSum"
SENT_RE = re.compile(r'(?<=[\.\!\?])\s+')

# --- Chargement modèle/tokenizer ---
# use_fast=False => évite l’exigence protobuf pour T5
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=False)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)
summarizer_pipe = pipeline("summarization", model=model, tokenizer=tokenizer)  # device=-1 (CPU) par défaut

def smart_chunks(text: str, max_chars=1800):
    # coupe sur fins de phrase pour éviter de casser les mots
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
    # dédoublonne, nettoie
    summary = re.sub(r'\s+', ' ', summary).strip()
    # supprime les phrases très courtes/bruit
    sents = [s for s in SENT_RE.split(summary) if len(s.strip()) >= 20]
    if lang == "fr":
        # filtre quelques tokens anglais fréquents
        sents = [s for s in sents if not re.search(r'\b(the|and|is|was)\b', s, re.I)]
    return " ".join(sents)

def summarize_text(text: str, max_length=150, min_length=60):
    if not text or not text.strip():
        return ""
    try:
        lang = detect(text[:1000])
    except Exception:
        lang = "fr"

    chunks = smart_chunks(text, max_chars=1800)
    outs = []
    for ch in chunks:
        try:
            out = summarizer_pipe(
                ch,
                max_length=max_length,
                min_length=min_length,
                do_sample=False
            )[0]["summary_text"]
        except Exception as e:
            # en cas d’erreur ponctuelle sur un chunk, on saute proprement
            out = ""
        if out:
            outs.append(out)

    merged = " ".join(outs)
    return postprocess(merged, lang=lang or "fr")
