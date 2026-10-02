"""
Retrieval hybride sur ChromaDB : sémantique + métadonnées.

- Détection du type de document dans la requête → bonus de re-ranking
- Re-ranking : score sémantique + overlap mots-clés + bonus doc_type
- Seuil de distance strict, sans fallback
"""
import json
import logging
import os
import unicodedata

import chromadb

from rag_pipeline.embeddings import EMBEDDING_MODEL, embed_texts

logger = logging.getLogger(__name__)

DOCS_COLLECTION_NAME = "pdf_documents"  # même nom que dans ingest.py

CHROMA_HOST  = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT  = int(os.getenv("CHROMA_PORT", "8000"))

# Seuil de pertinence : distance cosine > MAX_DISTANCE → chunk ignoré
MAX_DISTANCE = float(os.getenv("MAX_RETRIEVAL_DISTANCE", "0.8"))

# Sélection du document par son profil (questions courtes → seuil plus large)
DOC_TOP_K        = int(os.getenv("DOC_TOP_K", "3"))
DOC_MAX_DISTANCE = float(os.getenv("DOC_MAX_DISTANCE", "0.9"))
DOC_MARGIN       = float(os.getenv("DOC_MARGIN", "0.12"))  # écart toléré avec le meilleur
CHUNK_MARGIN     = float(os.getenv("CHUNK_MARGIN", "0.15"))  # idem pour les chunks

# Poids du re-ranking hybride
_W_SEMANTIC  = float(os.getenv("HYBRID_W_SEMANTIC", "0.7"))   # poids score sémantique
_W_KEYWORDS  = float(os.getenv("HYBRID_W_KEYWORDS", "0.2"))   # poids overlap mots-clés
_W_DOCTYPE   = float(os.getenv("HYBRID_W_DOCTYPE",  "0.1"))   # bonus type document


# ── Helpers NLP légers ────────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


_DOC_TYPE_HINTS: dict[str, list[str]] = {
    "CV":      ["cv", "curriculum", "candidat", "candidature", "competence",
                "experience", "formation", "diplome", "emploi", "poste", "recrutement",
                "stage", "stagiaire", "alternance", "apprentissage", "profil",
                "ingenieur", "developpeur", "technicien", "chef de projet"],
    "DEVIS":   ["devis", "prestation", "tarif", "prix", "estimation", "offre",
                "proposition commerciale", "forfait"],
    "FACTURE": ["facture", "paiement", "montant", "tva", "total", "reglement",
                "avoir", "bon de commande"],
    "CONTRAT": ["contrat", "accord", "clause", "engagement", "avenant",
                "convention", "signature"],
    "RAPPORT": ["rapport", "analyse", "etude", "bilan", "compte rendu", "synthese"],
}

_STOPWORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "au", "aux",
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "ce", "se",
    "que", "qui", "quoi", "ou", "dans", "sur", "avec", "pour", "par", "est",
    "sont", "a", "y", "ne", "pas", "plus", "bien", "tout", "tous", "toute",
}


def _query_words(query: str) -> set[str]:
    """Extrait les mots significatifs de la requête (sans accents, sans stopwords)."""
    words = _strip_accents(query.lower()).split()
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _detect_doc_type(query: str) -> str | None:
    """Détecte le type de document ciblé par la requête, ou None."""
    q = _strip_accents(query.lower())
    for doc_type, hints in _DOC_TYPE_HINTS.items():
        if any(h in q for h in hints):
            return doc_type
    return None


def _keyword_overlap(query_words: set[str], keywords: list) -> float:
    """Fraction des mots de la requête présents dans les mots-clés du chunk."""
    if not keywords or not query_words:
        return 0.0
    kw_words: set[str] = set()
    for kw in keywords:
        kw_words.update(_strip_accents(str(kw).lower()).split())
    return len(query_words & kw_words) / len(query_words)


def _parse_list_field(value) -> list:
    """Désérialise un champ liste stocké en JSON string dans ChromaDB."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


# Champs métadonnées stockés en JSON string (listes) → désérialisés pour l'affichage
_LIST_FIELDS = {
    "keywords", "entities", "topics", "domain", "key_points",
    "questions_answered", "hypothetical_questions", "concepts", "facts",
    "retrieval_nuggets", "amounts", "dates",
}


class ChatbotRetriever:

    def __init__(self, collection_name: str = "pdf_rag_collection"):
        self.collection_name = collection_name
        self.client = None

    @property
    def collection(self):
        """
        Collection relue à chaque accès : l'ingestion supprime/recrée la
        collection (nouvel id), une référence gardée en mémoire serait périmée.
        """
        if self.client is None:
            self.client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        return self.client.get_or_create_collection(
            name=self.collection_name, metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL}
        )

    # ── Formatage des résultats ───────────────────────────────────────────────

    def _format_results(self, results: dict) -> str:
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not documents:
            return "Aucun document pertinent trouvé dans la base de données."

        # Le filtrage par seuil est fait en amont dans get_context (avec fallback) :
        # ici on formate simplement ce qui a été retenu.
        rows = list(zip(documents, metadatas, distances or [None] * len(documents)))

        blocks = []
        for doc, meta, dist in rows:
            source       = meta.get("source", "Inconnu")
            doc_type     = meta.get("doc_type", "DOCUMENT")
            section_name = meta.get("section_name", "")
            doc_title    = meta.get("doc_title", "")
            page         = meta.get("page_number", "")
            local_sum    = meta.get("local_summary", "")
            keywords     = _parse_list_field(meta.get("keywords", ""))

            # Score de pertinence (distance → plus proche de 0 = plus pertinent)
            score_str = f"{1.0 / (1.0 + dist):.2f}" if dist is not None else "?"

            parts = [f"TYPE: {doc_type}", f"SOURCE: {source}"]
            if doc_title and doc_title != source:
                parts.append(f"TITRE: {doc_title}")
            if section_name:
                parts.append(f"EXTRAIT: {section_name}")
            if page:
                parts.append(f"PAGE: {page}")
            parts.append(f"SCORE: {score_str}")

            block = f"--- [{' | '.join(parts)}] ---\n{doc}"

            if local_sum:
                block += f"\n[Résumé: {local_sum}]"
            if keywords:
                block += f"\n[Mots-clés: {', '.join(keywords[:8])}]"

            blocks.append(block)

        return "\n\n".join(blocks)

    # ── Recherche hybride (sémantique + métadonnées) ─────────────────────────

    # ── Étape 1 : profils de documents (objectif, caractéristiques…) ──────────

    @property
    def docs_collection(self):
        if self.client is None:
            self.client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        return self.client.get_or_create_collection(
            name=DOCS_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL},
        )

    def _select_documents(self, q_vec) -> list[tuple[dict, float]]:
        """
        Documents dont le profil est proche de la question : [(meta, distance)].
        On garde le meilleur et ceux qui le suivent de près (DOC_MARGIN), dans
        la limite de DOC_TOP_K et de DOC_MAX_DISTANCE.
        """
        col = self.docs_collection
        total = col.count()
        if total == 0:
            return []
        res = col.query(
            query_embeddings=[q_vec],
            n_results=min(DOC_TOP_K, total),
            include=["metadatas", "distances"],
        )
        pairs = list(zip(res.get("metadatas", [[]])[0], res.get("distances", [[]])[0]))
        pairs.sort(key=lambda p: p[1])
        if not pairs or pairs[0][1] > DOC_MAX_DISTANCE:
            return []
        best = pairs[0][1]
        return [(m or {}, d) for m, d in pairs if d <= min(DOC_MAX_DISTANCE, best + DOC_MARGIN)]

    @staticmethod
    def _format_profiles(selected: list[tuple[dict, float]]) -> str:
        blocks = []
        for meta, dist in selected:
            lines = [f"--- [DOCUMENT: {meta.get('source', 'Inconnu')} | "
                     f"PROXIMITÉ: {1.0 / (1.0 + dist):.2f}] ---"]
            if meta.get("title"):
                lines.append(f"Titre : {meta['title']}")
            if meta.get("document_kind"):
                lines.append(f"Type : {meta['document_kind']}")
            if meta.get("subject"):
                lines.append(f"Sujet / propriétaire : {meta['subject']}")
            if meta.get("objective"):
                lines.append(f"Objectif : {meta['objective']}")
            chars = _parse_list_field(meta.get("characteristics", ""))
            if chars:
                lines.append("Caractéristiques : " + " ; ".join(chars))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    # ── Recherche en deux étapes : document (profil) puis chunks ─────────────

    def get_context(self, query: str, n_results: int = 12) -> str:
        """
        1. Les métadonnées de document (objectif, caractéristiques, sujet,
           générées par LLM) orientent vers le ou les bons documents par
           proximité avec la question.
        2. La recherche de chunks est restreinte à ces documents, puis re-rankée
           (score sémantique + mots-clés + bonus type).
        Si aucun profil ne correspond (ou index ancien sans profils), recherche
        globale sur les chunks avec seuil MAX_DISTANCE strict.
        """
        try:
            if self.collection.count() == 0:
                return "La base documentaire est vide : aucun document indexé."

            doc_type = _detect_doc_type(query)
            q_words  = _query_words(query)
            q_vec    = embed_texts([query])[0]
            fetch_n  = n_results * 3

            # ── Étape 1 : choix du/des documents ─────────────────────────────
            selected = self._select_documents(q_vec)
            ids = [m.get("document_id") for m, _ in selected if m.get("document_id")]
            logger.info(
                f"Recherche '{query[:60]}' → documents : "
                f"{[(m.get('source'), round(d, 3)) for m, d in selected] or 'aucun (recherche globale)'}"
            )

            # ── Étape 2 : chunks (restreints aux documents choisis) ──────────
            kwargs = dict(
                query_embeddings=[q_vec],
                include=["documents", "metadatas", "distances"],
            )
            if ids:
                pool = sum(int(m.get("chunk_count") or 0) for m, _ in selected) or fetch_n
                kwargs["where"] = {"document_id": {"$in": ids}}
                kwargs["n_results"] = max(1, min(fetch_n, pool))
            else:
                kwargs["n_results"] = max(1, min(fetch_n, self.collection.count()))
            results = self.collection.query(**kwargs)

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0] or [0.0] * len(documents)

            def _score(doc, meta, dist):
                meta = meta or {}
                sem_score = 1.0 / (1.0 + max(0.0, dist))
                kw_score  = _keyword_overlap(
                    q_words, _parse_list_field(meta.get("keywords", ""))
                )
                type_bonus = 1.0 if (doc_type and meta.get("doc_type") == doc_type) else 0.0
                hybrid = (_W_SEMANTIC * sem_score
                          + _W_KEYWORDS * kw_score
                          + _W_DOCTYPE  * type_bonus)
                return (doc, meta, dist, hybrid)

            all_scored = [_score(d, m, dist)
                          for d, m, dist in zip(documents, metadatas, distances)]

            # Un chunk n'est retenu que s'il est assez précis :
            #  - distance <= MAX_DISTANCE (seuil absolu)
            #  - et pas trop loin du meilleur chunk (CHUNK_MARGIN, seuil relatif)
            best_dist = min((s[2] for s in all_scored), default=None)
            scored = [s for s in all_scored
                      if s[2] <= MAX_DISTANCE and s[2] <= best_dist + CHUNK_MARGIN]
            if all_scored:
                logger.info(
                    f"  chunks : {len(scored)}/{len(all_scored)} retenus "
                    f"(seuil {MAX_DISTANCE}, marge {CHUNK_MARGIN}, min dist={best_dist:.3f})"
                )

            if not scored:
                best = f"{best_dist:.2f}" if best_dist is not None else "?"
                no_chunk = ("Aucun passage assez précis trouvé dans les documents indexés "
                            f"pour cette question (distance min {best} > seuil {MAX_DISTANCE}).")
                if selected:
                    # Le document est identifié, mais aucun passage n'est fiable :
                    # on renvoie sa fiche seule, sans passage non pertinent.
                    return f"{self._format_profiles(selected)}\n\n{no_chunk}"
                return no_chunk

            scored.sort(key=lambda x: x[3], reverse=True)
            top = scored[:n_results]
            passages = self._format_results({
                "documents": [[t[0] for t in top]],
                "metadatas": [[t[1] for t in top]],
                "distances": [[t[2] for t in top]],
            })

            if not selected:
                return passages
            # Blocs "--- [DOCUMENT: …] ---" puis "--- [TYPE: …] ---" : même format
            # que les passages, donc lisibles tels quels par le panneau Sources.
            return f"{self._format_profiles(selected)}\n\n{passages}"

        except Exception as e:
            logger.error(f"Erreur recherche ChromaDB : {e}")
            return "Erreur lors de la récupération du contexte."

    # ── Inventaire complet (pour l'onglet d'inspection) ───────────────────────

    def list_all_chunks(self) -> dict:
        """
        Retourne TOUS les chunks indexés, groupés par document source, avec leurs
        métadonnées complètes (listes JSON désérialisées).

        Forme :
          {
            "total": <int>,
            "documents": [
              {
                "document_id": str, "source": str, "doc_type": str,
                "doc_title": str, "chunk_count": int,
                "chunks": [
                  {"id", "text", "section_type", "section_name",
                   "chunk_index", "metadata": {...}}
                ]
              }, ...
            ]
          }
        """
        try:
            result = self.collection.get(include=["documents", "metadatas"])
        except Exception as e:
            logger.error(f"Erreur lecture ChromaDB (list_all_chunks) : {e}")
            return {"total": 0, "documents": [], "error": str(e)}

        ids   = result.get("ids", []) or []
        docs  = result.get("documents", []) or []
        metas = result.get("metadatas", []) or []

        grouped: dict[str, dict] = {}
        for cid, text, meta in zip(ids, docs, metas):
            meta = meta or {}
            doc_key = meta.get("document_id") or meta.get("source") or "inconnu"

            if doc_key not in grouped:
                grouped[doc_key] = {
                    "document_id": meta.get("document_id", ""),
                    "source":      meta.get("source", "Inconnu"),
                    "doc_type":    meta.get("doc_type", ""),
                    "doc_title":   meta.get("doc_title", ""),
                    "chunks":      [],
                }

            clean_meta = {
                k: (_parse_list_field(v) if k in _LIST_FIELDS else v)
                for k, v in meta.items()
            }

            grouped[doc_key]["chunks"].append({
                "id":           cid,
                "text":         text or "",
                "section_type": meta.get("section_type", ""),
                "section_name": meta.get("section_name", ""),
                "chunk_index":  meta.get("chunk_index", 0),
                "metadata":     clean_meta,
            })

        documents = []
        for d in grouped.values():
            d["chunks"].sort(
                key=lambda c: c["chunk_index"] if isinstance(c["chunk_index"], int) else 0
            )
            d["chunk_count"] = len(d["chunks"])
            documents.append(d)
        documents.sort(key=lambda d: d["source"])

        total = sum(d["chunk_count"] for d in documents)
        return {"total": total, "documents": documents}
