from langchain_core.tools import tool


@tool
def ingest_documents() -> str:
    """Lance l'ingestion, la classification et l'indexation de tous les PDF présents dans data/."""
    return "Ingestion en cours..."


@tool
def search_cv(query: str) -> str:
    """Recherche des informations dans les CVs (toutes sections : expériences, formation, langues…)."""
    return f"Recherche CV: {query}"


@tool
def search_cv_skills(query: str) -> str:
    """Recherche spécifiquement dans les sections de compétences des CVs. Utilise cet outil pour trouver les technologies, langages et outils maîtrisés."""
    return f"Recherche compétences CV: {query}"


@tool
def search_devis(query: str) -> str:
    """Recherche des informations ou clauses spécifiquement dans les devis."""
    return f"Recherche devis: {query}"


@tool
def search_global(query: str) -> str:
    """Effectue une recherche globale à travers tous les documents disponibles."""
    return f"Recherche globale: {query}"


def get_tools_list():
    return [ingest_documents, search_cv, search_cv_skills, search_devis, search_global]
