"""
Génération de métadonnées structurées pour documents et chunks.

Stratégie 100 % CPU, sans LLM par défaut :
- Métadonnées document : YAKE (mots-clés) + TextRank (résumé) + regex
  (entités, dates, montants…). Aucun appel LLM.
- Métadonnées chunk : heuristiques (YAKE + regex) par défaut. Un appel LLM
  n'a lieu QUE si ENRICH_CHUNKS=true (coûteux sur CPU, déconseillé).

Garanties :
- Ne propage jamais d'exception (fallback systématique)
- Valide les sorties avec Pydantic (v2)
- Sérialise les listes en JSON string pour compatibilité ChromaDB
- Les scores sont clampés dans [0.0, 1.0]
"""
import json
import logging
import os
import re

from pydantic import BaseModel, Field, field_validator

from rag_pipeline.text_analysis import (
    extract_keywords,
    extract_summary,
    extract_universal_fields,
    guess_author_and_org,
)

logger = logging.getLogger(__name__)

# ── Regex pour extraire le JSON de la réponse LLM ────────────────────────────

_JSON_FENCE   = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_JSON_OBJECT  = re.compile(r"\{[\s\S]*\}", re.DOTALL)


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class DocumentMeta(BaseModel):
    """Métadonnées de niveau document générées par LLM."""

    title:                  str         = ""
    language:               str         = "fr"
    author:                 str         = ""
    organization:           str         = ""
    creation_date:          str         = ""
    domain:                 list[str]   = Field(default_factory=list)
    topics:                 list[str]   = Field(default_factory=list)
    keywords:               list[str]   = Field(default_factory=list)
    entities:               list[str]   = Field(default_factory=list)
    summary:                str         = ""
    key_points:             list[str]   = Field(default_factory=list)
    questions_answered:     list[str]   = Field(default_factory=list)
    hypothetical_questions: list[str]   = Field(default_factory=list)
    sensitivity:            str         = "public"
    confidence_score:       float       = 0.0

    @field_validator("confidence_score")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("domain", "topics", "keywords", "entities",
                     "key_points", "questions_answered", "hypothetical_questions",
                     mode="before")
    @classmethod
    def ensure_list(cls, v) -> list:
        if isinstance(v, str):
            return [v] if v else []
        return v if isinstance(v, list) else []


class ChunkMeta(BaseModel):
    """Métadonnées de niveau chunk générées par LLM ou heuristiques."""

    chunk_title:            str         = ""
    local_summary:          str         = ""
    keywords:               list[str]   = Field(default_factory=list)
    entities:               list[str]   = Field(default_factory=list)
    concepts:               list[str]   = Field(default_factory=list)
    facts:                  list[str]   = Field(default_factory=list)
    questions_answered:     list[str]   = Field(default_factory=list)
    hypothetical_questions: list[str]   = Field(default_factory=list)
    retrieval_nuggets:      list[str]   = Field(default_factory=list)
    importance_score:       float       = 0.5
    confidence_score:       float       = 0.0

    @field_validator("importance_score", "confidence_score")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("keywords", "entities", "concepts", "facts",
                     "questions_answered", "hypothetical_questions", "retrieval_nuggets",
                     mode="before")
    @classmethod
    def ensure_list(cls, v) -> list:
        if isinstance(v, str):
            return [v] if v else []
        return v if isinstance(v, list) else []


# ── Sérialisation ChromaDB ────────────────────────────────────────────────────

def flatten_for_chroma(meta: DocumentMeta | ChunkMeta) -> dict:
    """
    ChromaDB n'accepte que str / int / float / bool comme valeurs de métadonnées.
    Les listes et dicts sont sérialisés en JSON string.
    None → "".
    """
    result = {}
    for field_name, value in meta.model_dump().items():
        if isinstance(value, (list, dict)):
            result[field_name] = json.dumps(value, ensure_ascii=False)
        elif value is None:
            result[field_name] = ""
        else:
            result[field_name] = value
    return result


def parse_chroma_list(value: str) -> list:
    """Désérialise un champ liste stocké en JSON string dans ChromaDB."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ── Extraction JSON depuis la réponse LLM ─────────────────────────────────────

def _extract_json_from_llm(text: str) -> dict:
    """
    Tente d'extraire un objet JSON valide depuis la réponse brute du LLM.
    1. Cherche un bloc ```json ... ```
    2. Fallback : premier {...} dans le texte
    3. Fallback final : {}
    """
    m = _JSON_FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    m = _JSON_OBJECT.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Impossible d'extraire un JSON valide de la réponse LLM.")
    return {}


# ── Générateur principal ──────────────────────────────────────────────────────

class MetadataGenerator:
    """
    Génère des métadonnées structurées pour documents et chunks.

    Par défaut tout est calculé sans LLM (YAKE + TextRank + regex). Le LLM
    n'est instancié paresseusement que si ENRICH_CHUNKS=true, uniquement pour
    l'enrichissement par chunk.

    Variables d'environnement :
      OLLAMA_BASE_URL  — URL du serveur Ollama (si ENRICH_CHUNKS=true)
      OLLAMA_MODEL     — Modèle à utiliser (si ENRICH_CHUNKS=true)
      ENRICH_CHUNKS    — "true" pour activer le LLM par chunk (défaut : false)
    """

    def __init__(self):
        self._enrich_chunks = os.getenv("ENRICH_CHUNKS", "false").lower() == "true"
        self._llm = None  # instancié paresseusement (voir _get_llm)

    # ── LLM paresseux (seulement si ENRICH_CHUNKS=true) ────────────────────────

    def _get_llm(self):
        """Instancie ChatOllama à la demande pour ne rien charger sur CPU par défaut."""
        if self._llm is None:
            from langchain_ollama import ChatOllama

            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
            model      = os.getenv("PROFILE_MODEL") or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
            self._llm  = ChatOllama(model=model, base_url=ollama_url, temperature=0.0)
        return self._llm

    def _call_llm_json(self, system_prompt: str, user_content: str) -> dict:
        """
        Appelle le LLM et retourne un dict JSON.
        Ne propage jamais d'exception : retourne {} en cas d'échec.
        """
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            response = self._get_llm().invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ])
            raw = response.content.strip()
            data = _extract_json_from_llm(raw)
            if not isinstance(data, dict):
                logger.warning("Réponse LLM non-dict après extraction JSON.")
                return {}
            return data
        except Exception as e:
            logger.warning(f"Erreur appel LLM métadonnées : {e}")
            return {}

    # ── Métadonnées document (sans LLM) ────────────────────────────────────────

    def generate_document_metadata(
        self, full_text: str, filename: str, doc_type: str
    ) -> DocumentMeta:
        """
        Génère les métadonnées de niveau document SANS LLM :
          - keywords  : YAKE (mots-clés multi-mots statistiques)
          - summary   : TextRank (résumé extractif)
          - entities  : regex (emails) + heuristique auteur/organisation
          - creation_date / amounts / dates : extraction regex universelle
        Ne propage jamais d'exception.
        """
        try:
            keywords = extract_keywords(full_text, lang="fr", top_k=12)
            summary  = extract_summary(full_text, max_sentences=3)
            fields   = extract_universal_fields(full_text)
            author, organization = guess_author_and_org(full_text)

            # Titre : première ligne courte non vide, sinon nom de fichier nettoyé.
            title = ""
            for line in full_text.splitlines():
                line = line.strip()
                if 3 <= len(line) <= 90:
                    title = line
                    break
            if not title:
                title = filename.replace(".pdf", "").replace("_", " ")

            entities = list(dict.fromkeys(fields["emails"] + ([organization] if organization else [])))

            return DocumentMeta(
                title=title[:120],
                language="fr",
                author=author,
                organization=organization,
                creation_date=(fields["dates"][0] if fields["dates"] else ""),
                domain=keywords[:2],
                topics=keywords[:6],
                keywords=keywords,
                entities=entities[:10],
                summary=summary[:600],
                key_points=[s.strip() for s in re.split(r"(?<=[.!?])\s+", summary) if s.strip()][:5],
                sensitivity="public",
                confidence_score=0.5,
            )
        except Exception as e:
            logger.warning(f"Génération métadonnées document échouée : {e}. Valeurs par défaut.")
            return DocumentMeta(
                title=filename.replace(".pdf", "").replace("_", " "),
                summary=f"Document de type {doc_type} — métadonnées non générées.",
                confidence_score=0.1,
            )

    # ── Métadonnées chunk ─────────────────────────────────────────────────────

    def generate_chunk_metadata(
        self, chunk_text: str, section_name: str, doc_title: str = ""
    ) -> ChunkMeta:
        """
        Génère les métadonnées d'un chunk.
        Si ENRICH_CHUNKS=false (défaut), utilise les heuristiques (rapide, sans LLM).
        Si ENRICH_CHUNKS=true, appelle le LLM (précis mais coûteux sur CPU).
        """
        if not self._enrich_chunks:
            return self._heuristic_chunk_meta(chunk_text, section_name)

        system = (
            "Tu es un expert en extraction d'information. "
            "Génère des métadonnées structurées pour un extrait de document professionnel. "
            "Réponds UNIQUEMENT avec un objet JSON valide. Pas de balises Markdown."
        )
        user = (
            f"Document : {doc_title} | Section : {section_name}\n"
            f"Extrait :\n{chunk_text[:800]}\n\n"
            "Génère un JSON avec EXACTEMENT ces champs :\n"
            "{\n"
            '  "chunk_title": "titre court de cet extrait",\n'
            '  "local_summary": "résumé en 1-2 phrases",\n'
            '  "keywords": ["mot-clé"],\n'
            '  "entities": ["entité nommée"],\n'
            '  "concepts": ["concept abstrait"],\n'
            '  "facts": ["fait établi dans cet extrait"],\n'
            '  "questions_answered": ["question à laquelle cet extrait répond"],\n'
            '  "hypothetical_questions": ["requête qui trouverait cet extrait utile"],\n'
            '  "retrieval_nuggets": ["phrase verbatim clé pour la recherche"],\n'
            '  "importance_score": 0.7,\n'
            '  "confidence_score": 0.8\n'
            "}"
        )

        data = self._call_llm_json(system, user)
        try:
            return ChunkMeta.model_validate(data)
        except Exception as e:
            logger.warning(f"Validation ChunkMeta échouée : {e}. Fallback heuristique.")
            return self._heuristic_chunk_meta(chunk_text, section_name)

    # ── Fallback heuristique (sans LLM) ──────────────────────────────────────

    def _heuristic_chunk_meta(self, chunk_text: str, section_name: str) -> ChunkMeta:
        """
        Extraction heuristique rapide (sans LLM) : mots-clés YAKE, entités regex.
        Toujours disponible, même sans Ollama.
        """
        # Entités : mots commençant par une majuscule (NP heuristique)
        entities = list(dict.fromkeys(
            re.findall(r"\b[A-ZÀ-Ÿ][a-zà-ÿA-ZÀ-Ÿ]{2,}\b", chunk_text)
        ))[:10]

        # Mots-clés : YAKE (fallback fréquence intégré dans extract_keywords)
        keywords = extract_keywords(chunk_text, lang="fr", top_k=10)

        # Résumé local : première phrase significative
        first_sentence = next(
            (s.strip() for s in re.split(r"[.!?\n]", chunk_text) if len(s.strip()) > 20),
            chunk_text[:120],
        )

        return ChunkMeta(
            chunk_title=section_name[:80],
            local_summary=first_sentence[:200],
            keywords=keywords,
            entities=entities,
            importance_score=0.5,
            confidence_score=0.2,
        )
