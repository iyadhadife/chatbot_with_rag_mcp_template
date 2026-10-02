"""
Profil de document généré par LLM (1 appel par document) et indexé dans une
collection dédiée : un vecteur par document.

À la recherche, c'est ce profil (objectif, caractéristiques, sujet) qui oriente
vers le bon document par proximité ; la recherche de chunks est ensuite
restreinte à ces documents.
"""
import json
import logging

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_MAX_CHARS = 7000  # début + fin du document suffisent pour un profil

_SYSTEM = """Tu analyses un document et tu produis sa fiche d'identité.
Réponds UNIQUEMENT par un objet JSON avec ces clés :
- "title" : titre court du document
- "document_kind" : nature du document (CV, devis, facture, contrat, rapport, cours, etc.)
- "subject" : de QUI ou de QUOI parle le document (nom de la personne, de l'entreprise, du projet)
- "objective" : à quoi sert ce document, en 1 ou 2 phrases
- "characteristics" : liste de 4 à 8 caractéristiques distinctives (compétences, technologies, montants, dates, lieux, parties concernées...)
- "summary" : résumé en 2 ou 3 phrases
Écris en français. N'invente rien : utilise uniquement le texte fourni."""


class DocumentProfile(BaseModel):
    title:           str       = ""
    document_kind:   str       = ""
    subject:         str       = ""
    objective:       str       = ""
    characteristics: list[str] = Field(default_factory=list)
    summary:         str       = ""

    @field_validator("title", "document_kind", "subject", "objective", "summary",
                     mode="before")
    @classmethod
    def _to_str(cls, v) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return "" if v is None else str(v)

    @field_validator("characteristics", mode="before")
    @classmethod
    def _to_list(cls, v) -> list:
        if isinstance(v, str):
            return [v] if v else []
        return [str(x) for x in v] if isinstance(v, list) else []

    def to_text(self) -> str:
        """Texte embeddé : c'est lui qui est comparé à la question."""
        parts = [
            self.title,
            f"Type : {self.document_kind}" if self.document_kind else "",
            f"Sujet : {self.subject}" if self.subject else "",
            f"Objectif : {self.objective}" if self.objective else "",
            "Caractéristiques : " + " ; ".join(self.characteristics) if self.characteristics else "",
            f"Résumé : {self.summary}" if self.summary else "",
        ]
        return "\n".join(p for p in parts if p)

    def to_chroma(self) -> dict:
        return {
            "title":           self.title,
            "document_kind":   self.document_kind,
            "subject":         self.subject,
            "objective":       self.objective,
            "characteristics": json.dumps(self.characteristics, ensure_ascii=False),
            "summary":         self.summary,
        }


def generate_document_profile(generator, full_text: str, filename: str,
                              fallback_title: str, fallback_summary: str,
                              doc_type: str) -> DocumentProfile:
    """Profil via LLM ; repli sur les métadonnées heuristiques si le LLM échoue."""
    excerpt = full_text
    if len(excerpt) > _MAX_CHARS:
        half = _MAX_CHARS // 2
        excerpt = excerpt[:half] + "\n[...]\n" + excerpt[-half:]

    data = generator._call_llm_json(_SYSTEM, f"Fichier : {filename}\n\n{excerpt}")
    try:
        profile = DocumentProfile(**{k: data[k] for k in DocumentProfile.model_fields if k in data})
    except Exception as e:
        logger.warning(f"Profil LLM invalide ({e}) → repli heuristique.")
        profile = DocumentProfile()

    if not (profile.objective or profile.subject or profile.summary):
        logger.warning(f"  ⚠ Profil LLM vide pour {filename} → repli heuristique.")
        profile.summary = fallback_summary
    profile.title = profile.title or fallback_title or filename
    profile.document_kind = profile.document_kind or doc_type
    return profile
