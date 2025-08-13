# utils/keywords.py
import re
import yake

def extract_keywords(text, max_keywords=12, language="fr"):
    # combine 1,2,3-grams
    all_kw = {}
    for n in (1, 2, 3):
        kw_extractor = yake.KeywordExtractor(lan=language, n=n, top=max_keywords)
        for kw, score in kw_extractor.extract_keywords(text):
            k = kw.strip()
            # filtre: pas d’adresse/numéro/URL/propre nom “trop” majuscule
            if re.search(r'(https?://|www\.|@\w+|\d{2,}|\bQC\b|H[0-9A-Z]{3,})', k):
                continue
            if len(k) < 3:
                continue
            all_kw[k.lower()] = min(score, all_kw.get(k.lower(), 1e9))
    # tri par score (plus petit = meilleur)
    cleaned = sorted(all_kw.items(), key=lambda x: x[1])
    return [k for k,_ in cleaned[:max_keywords]]
