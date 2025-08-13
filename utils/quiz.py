import re
import random
from typing import List, Dict, Optional

SENTENCE_SPLIT_RE = re.compile(r'(?<=[\.\!\?])\s+')
NEGATION_PATTERNS = [
    r"\bne\b.*\bpas\b",
    r"\bn'[^ ]+\b.*\bpas\b",
    r"\bjamais\b",
    r"\baucun(e|s)?\b",
    r"\bplus\b",
    r"\bsans\b",
]

def normalize_space(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()

def split_sentences(text: str) -> List[str]:
    text = normalize_space(text)
    sents = SENTENCE_SPLIT_RE.split(text)
    # Nettoyage basique
    return [s.strip() for s in sents if len(s.strip()) > 20]

def find_sentence_with_keyword(sentences: List[str], kw: str) -> Optional[str]:
    kw_re = re.compile(rf'\b{re.escape(kw)}\b', flags=re.IGNORECASE)
    for s in sentences:
        if kw_re.search(s):
            return s
    return None

def contains_negation(s: str) -> bool:
    s_norm = f" {normalize_space(s).lower()} "
    return any(re.search(pat, s_norm, flags=re.IGNORECASE) for pat in NEGATION_PATTERNS)

def is_exact_sentence(candidate: str, sentences_set: set) -> bool:
    # comparaison insensible aux espaces
    return normalize_space(candidate) in sentences_set

def mask_keyword(sentence: str, keyword: str) -> str:
    # Masquage robuste insensible à la casse, garde la ponctuation
    return re.sub(rf'\b{re.escape(keyword)}\b', '____', sentence, flags=re.IGNORECASE)

def pick_distractors(keyword: str, pool: List[str], k: int) -> List[str]:
    # Distracteurs uniques, pas trop proches, longueur similaire
    key_lower = keyword.lower()
    uniq = []
    for d in pool:
        d = d.strip()
        if not d or d.lower() == key_lower or len(d) < 3:
            continue
        # évite variantes trop proches
        if d.lower() in {x.lower() for x in uniq}:
            continue
        if abs(len(d) - len(keyword)) <= max(2, len(keyword)//3):
            uniq.append(d)
        if len(uniq) >= k:
            break
    return uniq

def build_mcq_from_sentence(sentence: str, keyword: str, distractors_pool: List[str], k_choices: int = 4) -> Dict:
    masked = mask_keyword(sentence, keyword)

    # Distracteurs plus qualitatifs
    distractors = pick_distractors(keyword, distractors_pool, k_choices - 1)

    # Si pool insuffisant, complète proprement
    i = 1
    while len(distractors) < (k_choices - 1):
        filler = f"{keyword[:max(3, len(keyword)//2)]}{i}"
        if filler.lower() != keyword.lower() and filler.lower() not in {x.lower() for x in distractors}:
            distractors.append(filler)
        i += 1

    # Assemble choix et réponse
    choices = distractors + [keyword]
    random.shuffle(choices)
    answer_index = choices.index(keyword)

    return {
        "type": "mcq",
        "question": f"Complète la phrase : « {masked} »",
        "choices": choices,
        "answer_index": answer_index,
        "answer": keyword,
        "explanation": f"Le mot manquant est « {keyword} » tel qu'il apparaît dans le texte d'origine."
    }

# --- Génération Vrai/Faux selon la règle demandée ---

NEGATION_INJECT_PATTERNS = [
    # essais simples pour insérer 'ne ... pas' après des verbes fréquents
    (r"\b(est|sont|était|étaient|sera|seront)\b", r" \1 ne ... pas "),
    (r"\b(a|ont|avait|avaient|aura|auront)\b", r" \1 ne ... pas "),
]

def inject_negation(sentence: str) -> str:
    """Essaie de créer une version négative lisible de la phrase.
    Fallback: ajoute ' (négation)' si on ne peut pas modifier proprement.
    """
    s = normalize_space(sentence)

    # Évite de doubler une négation si elle existe déjà
    if contains_negation(s):
        return s

    # Insertion simple de 'ne ... pas' autour de quelques auxiliaires courants
    for pat, repl in NEGATION_INJECT_PATTERNS:
        if re.search(pat, s, flags=re.IGNORECASE):
            # Heuristique simple : insérer 'ne ... pas' après l’auxiliaire détecté
            s2 = re.sub(pat, lambda m: m.group(0) + " ne", s, flags=re.IGNORECASE, count=1)
            # insère 'pas' après le prochain mot
            s2 = re.sub(r"\bne\s+(\S+)\b", r"ne \1 pas", s2, count=1)
            return s2

    # Autres formes négatives si l’auxiliaire n'est pas détecté
    # Exemple: préfixer "Il n'est pas vrai que ..."
    if not s.lower().startswith(("il n'est pas vrai que", "ce n'est pas vrai que")):
        return f"Il n'est pas vrai que {s[0].lower() + s[1:] if s else s}"

    # Fallback ultime
    return s + " (négation)"

def make_true_false_questions(sentences: List[str], need: int, used: set) -> List[Dict]:
    """Crée des énoncés où:
      - VRAI: phrase EXACTE du texte
      - FAUX: version NEGATIVE de la phrase
    """
    out: List[Dict] = []
    sentences_clean = [normalize_space(s) for s in sentences]
    sentences_set = set(sentences_clean)

    # on pioche des phrases non encore utilisées
    pool = [s for s in sentences_clean if s not in used and len(s) >= 20]
    random.shuffle(pool)

    for s in pool:
        if len(out) >= need:
            break

        # Alterner Vrai/Faux pour diversité
        if len(out) % 2 == 0:
            # VRAI : phrase identique
            stmt_true = s
            out.append({
                "type": "true_false",
                "statement": stmt_true,
                "answer": True,
                "explanation": "Énoncé identique à une phrase du texte → Vrai."
            })
            used.add(s)
        else:
            # FAUX : phrase négative construite
            neg = inject_negation(s)
            # S'assurer que la version négative n'est pas exactement une phrase du texte
            if is_exact_sentence(neg, sentences_set):
                neg = "Il n'est pas vrai que " + s[0].lower() + s[1:]
            out.append({
                "type": "true_false",
                "statement": neg,
                "answer": False,
                "explanation": "La phrase contient une négation/inversion du sens par rapport au texte → Faux."
            })
            used.add(s)

    return out

def generate_quiz(text: str, keywords: List[str], num_questions: int = 5) -> List[Dict]:
    random.seed(42)  # stabilité des tests
    sentences = split_sentences(text)
    sentences_norm = [normalize_space(s) for s in sentences]

    # Priorise les keywords plus “informatifs” (longueur décroissante)
    kws = sorted({k.strip() for k in keywords if len((k or "").strip()) >= 3}, key=len, reverse=True)

    questions: List[Dict] = []
    used_sentences = set()

    # 1) MCQ à partir de phrases qui contiennent un mot-clé
    for kw in kws:
        if len(questions) >= num_questions:
            break
        sent = find_sentence_with_keyword(sentences, kw)
        if not sent:
            continue
        sent_n = normalize_space(sent)
        if sent_n in used_sentences:
            continue

        q = build_mcq_from_sentence(sent, kw, distractors_pool=list(kws))
        questions.append(q)
        used_sentences.add(sent_n)

    # 2) Complète avec des Vrai/Faux suivant la règle demandée
    missing = num_questions - len(questions)
    if missing > 0:
        tf_qs = make_true_false_questions(sentences, missing, used_sentences)
        questions.extend(tf_qs)

    return questions
