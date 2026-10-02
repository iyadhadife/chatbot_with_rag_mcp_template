"""
Analyse de texte légère, 100 % CPU, sans LLM.

Quatre outils statistiques / algorithmiques remplacent les appels LLM de
l'ingestion (classification + métadonnées document) :

  1. classify_document_type()  — classifieur à base de règles (scoring de
     vocabulaire). Zéro dépendance, zéro entraînement, instantané.
  2. extract_keywords()        — mots-clés multi-mots via YAKE (statistique,
     non neuronal).
  3. extract_summary()         — résumé extractif via TextRank (graphe de
     phrases + PageRank, implémenté avec networkx). Pas de sumy/nltk, donc
     aucun téléchargement de modèle au build Docker.
  4. extract_universal_fields()— extraction regex universelle : emails,
     téléphones, montants, dates, SIRET, IBAN, TVA.

Aucune de ces fonctions ne propage d'exception : elles renvoient toujours une
valeur par défaut raisonnable.
"""
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


def _strip_accents(text: str) -> str:
    """Replie les accents (é→e, à→a…) pour une comparaison robuste."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


# ── 1. Classification à base de règles ────────────────────────────────────────

VALID_DOC_TYPES = {"CV", "DEVIS", "FACTURE", "CONTRAT", "RAPPORT", "AUTRE"}

# Vocabulaire discriminant par type. Chaque terme est testé avec une frontière
# de mot (\b), insensible à la casse. Un document est classé selon le type qui
# cumule le plus de termes distincts trouvés.
_TYPE_VOCAB: dict[str, list[str]] = {
    "CV": [
        "compétences", "compétence", "expériences", "expérience professionnelle",
        "formation", "diplôme", "diplômes", "langues", "curriculum vitae",
        "parcours", "stage", "projets", "certifications", "loisirs",
        "centres d'intérêt", "cv",
    ],
    "DEVIS": [
        "devis", "prestation", "prestations", "montant ht", "montant ttc",
        "tva", "ttc", "prix unitaire", "quantité", "conditions de paiement",
        "bon pour accord", "validité du devis", "acompte", "règlement",
        "total ht", "total ttc", "net à payer",
    ],
    "FACTURE": [
        "facture", "facturation", "n° de facture", "numéro de facture",
        "date d'échéance", "échéance", "à payer", "déjà réglé",
    ],
    "CONTRAT": [
        "contrat", "les parties", "clause", "résiliation", "obligations",
        "signataire", "présent contrat", "article premier", "entre les soussignés",
    ],
    "RAPPORT": [
        "rapport", "méthodologie", "introduction", "conclusion", "synthèse",
        "résultats", "analyse", "recommandations", "sommaire",
    ],
}

# Termes fortement discriminants : comptent double dans le scoring.
_STRONG_TERMS = {
    "DEVIS": {"devis", "bon pour accord", "validité du devis", "net à payer"},
    "CV": {"curriculum vitae", "compétences", "centres d'intérêt"},
    "FACTURE": {"facture", "n° de facture", "numéro de facture"},
    "CONTRAT": {"présent contrat", "entre les soussignés", "clause"},
    "RAPPORT": {"méthodologie", "synthèse"},
}


def classify_document_type(text_sample: str) -> str:
    """
    Classifie le type de document par scoring de vocabulaire (sans LLM).

    Renvoie toujours un type valide. Fallback : "AUTRE" si aucun type ne
    réunit au moins 2 termes distincts (évite les faux positifs).
    """
    if not text_sample or not text_sample.strip():
        return "AUTRE"

    # Insensible aux accents : les PDF perdent parfois les accents à l'extraction.
    text = _strip_accents(text_sample.lower())
    scores: dict[str, int] = {}

    for doc_type, terms in _TYPE_VOCAB.items():
        strong = {_strip_accents(t) for t in _STRONG_TERMS.get(doc_type, set())}
        distinct_hits = 0
        weighted = 0
        for term in terms:
            folded = _strip_accents(term)
            pattern = r"(?<![\w])" + re.escape(folded) + r"(?![\w])"
            if re.search(pattern, text):
                distinct_hits += 1
                weighted += 2 if folded in strong else 1
        # On garde le nombre de termes distincts comme critère principal,
        # pondéré par les termes forts en cas d'égalité.
        scores[doc_type] = distinct_hits * 100 + weighted

    best_type = max(scores, key=scores.get)
    best_distinct = scores[best_type] // 100

    if best_distinct < 2:
        logger.info("Classification par règles : aucun type dominant, fallback AUTRE.")
        return "AUTRE"
    return best_type


# ── 2. Mots-clés (YAKE) ───────────────────────────────────────────────────────

_YAKE_STOPWORDS = {
    "dans", "pour", "avec", "sont", "cette", "nous", "vous", "tout", "plus",
    "mais", "avoir", "être", "faire", "bien", "aussi", "comme", "entre",
}


def extract_keywords(text: str, lang: str = "fr", top_k: int = 12) -> list[str]:
    """
    Extrait des mots-clés multi-mots via YAKE (statistique, CPU, sans modèle).
    Fallback : fréquence des termes ≥ 5 caractères hors stopwords.
    """
    text = (text or "").strip()
    if not text:
        return []

    try:
        import yake

        extractor = yake.KeywordExtractor(
            lan=lang, n=2, dedupLim=0.7, top=top_k, features=None
        )
        pairs = extractor.extract_keywords(text)
        # YAKE : score bas = plus pertinent → déjà triés croissant.
        keywords = [kw.strip() for kw, _score in pairs if kw.strip()]
        if keywords:
            return keywords[:top_k]
    except Exception as e:
        logger.warning(f"YAKE indisponible ({e}), fallback fréquence.")

    # Fallback purement fréquentiel
    words = re.findall(r"\b[a-zà-ÿA-ZÀ-Ÿ]{5,}\b", text.lower())
    ordered = [w for w in dict.fromkeys(words) if w not in _YAKE_STOPWORDS]
    return ordered[:top_k]


# ── 3. Résumé extractif (TextRank) ────────────────────────────────────────────

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ÿ0-9])")


def _split_sentences(text: str) -> list[str]:
    """Découpe naïve en phrases (sans nltk)."""
    # Normaliser les sauts de ligne en espaces pour ne pas sur-découper.
    flat = re.sub(r"\s*\n\s*", " ", text.strip())
    raw = _SENTENCE_SPLIT.split(flat)
    return [s.strip() for s in raw if len(s.strip()) > 15]


def extract_summary(text: str, max_sentences: int = 3) -> str:
    """
    Résumé extractif via TextRank : construit un graphe de similarité entre
    phrases puis applique PageRank (networkx). Sélectionne les phrases les plus
    centrales et les restitue dans l'ordre d'origine.
    Fallback : premières phrases du texte.
    """
    text = (text or "").strip()
    if not text:
        return ""

    sentences = _split_sentences(text)
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    try:
        import networkx as nx

        # Sacs de mots par phrase (minuscules, ≥ 3 chars, hors stopwords).
        token_sets = []
        for s in sentences:
            toks = {
                w for w in re.findall(r"\b[a-zà-ÿA-ZÀ-Ÿ]{3,}\b", s.lower())
                if w not in _YAKE_STOPWORDS
            }
            token_sets.append(toks)

        graph = nx.Graph()
        graph.add_nodes_from(range(len(sentences)))
        for i in range(len(sentences)):
            for j in range(i + 1, len(sentences)):
                a, b = token_sets[i], token_sets[j]
                if not a or not b:
                    continue
                overlap = len(a & b)
                if overlap == 0:
                    continue
                import math

                norm = math.log(len(a) + 1) + math.log(len(b) + 1)
                weight = overlap / norm if norm else 0.0
                if weight > 0:
                    graph.add_edge(i, j, weight=weight)

        ranks = nx.pagerank(graph, weight="weight")
        top_idx = sorted(ranks, key=ranks.get, reverse=True)[:max_sentences]
        top_idx.sort()  # ordre d'origine
        return " ".join(sentences[i] for i in top_idx)
    except Exception as e:
        logger.warning(f"TextRank indisponible ({e}), fallback premières phrases.")
        return " ".join(sentences[:max_sentences])


# ── 4. Extraction universelle par regex ───────────────────────────────────────

_RE_EMAIL  = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_PHONE  = re.compile(r"(?:(?:\+33|0033|0)\s?[1-9])(?:[\s.-]?\d{2}){4}\b")
_RE_AMOUNT = re.compile(r"\b\d[\d\s.,]*\s?(?:€|EUR|euros?|\$|USD)\b", re.IGNORECASE)
_RE_DATE   = re.compile(
    r"\b(?:\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|"
    r"septembre|octobre|novembre|décembre)\s+\d{4})\b",
    re.IGNORECASE,
)
_RE_SIRET  = re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\s?\d{5}\b")
_RE_IBAN   = re.compile(r"\bFR\d{2}(?:\s?[A-Z0-9]{4}){5,7}\b")
_RE_TVA    = re.compile(r"(?:TVA|T\.V\.A\.)\D{0,15}?(\d{1,2}(?:[.,]\d)?)\s?%", re.IGNORECASE)


def _dedup(seq: list[str]) -> list[str]:
    return list(dict.fromkeys(s.strip() for s in seq if s.strip()))


def extract_universal_fields(text: str) -> dict:
    """
    Extrait les champs structurés communs à tout document via regex.
    Toujours sûr : renvoie des listes (vides si rien trouvé).
    """
    text = text or ""
    tva_matches = [m.group(1) for m in _RE_TVA.finditer(text)]
    return {
        "emails":  _dedup(_RE_EMAIL.findall(text))[:10],
        "phones":  _dedup(_RE_PHONE.findall(text))[:10],
        "amounts": _dedup(_RE_AMOUNT.findall(text))[:20],
        "dates":   _dedup(_RE_DATE.findall(text))[:20],
        "siret":   _dedup(_RE_SIRET.findall(text))[:5],
        "iban":    _dedup(_RE_IBAN.findall(text))[:5],
        "tva_rates": _dedup(tva_matches)[:5],
    }


# ── Heuristiques auteur / organisation (best-effort, sans NER) ─────────────────

_ORG_SUFFIX = re.compile(
    r"\b[A-ZÀ-Ÿ][\wÀ-ÿ&'’.\- ]{1,60}?\s(?:SARL|SAS|SASU|SA|EURL|SCI|SNC|"
    r"GIE|Inc|Ltd|LLC|GmbH|Corp)\b"
)
_NAME_LINE = re.compile(r"^[A-ZÀ-Ÿ][a-zà-ÿ]+(?:[\s-][A-ZÀ-Ÿ][a-zà-ÿ]+){1,2}$")


def guess_author_and_org(full_text: str) -> tuple[str, str]:
    """
    Devine auteur et organisation par heuristiques simples (sans SpaCy).
      - organisation : premier motif « <Nom> SARL/SAS/... », sinon domaine email.
      - auteur : première ligne ressemblant à un nom propre (2–3 mots capitalisés).
    Renvoie ("", "") si rien de fiable.
    """
    author, organization = "", ""

    org_match = _ORG_SUFFIX.search(full_text)
    if org_match:
        organization = org_match.group(0).strip()
    else:
        email_match = _RE_EMAIL.search(full_text)
        if email_match:
            domain = email_match.group(0).split("@")[-1].split(".")[0]
            if domain and domain not in {"gmail", "outlook", "hotmail", "yahoo", "free", "orange"}:
                organization = domain.capitalize()

    for line in full_text.splitlines()[:15]:
        line = line.strip()
        if _NAME_LINE.match(line):
            author = line
            break

    return author, organization
