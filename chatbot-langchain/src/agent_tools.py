from langchain_core.tools import tool


@tool
def ingest_documents() -> str:
    """Lance l'ingestion et l'indexation de tous les PDF présents dans data/pdfs."""
    return "Ingestion en cours..."


@tool
def search_documents(query: str) -> str:
    """Recherche des informations dans la base documentaire (CV, devis, factures,
    contrats…). Unique outil de recherche : utilise-le pour toute question portant
    sur le contenu des documents."""
    return f"Recherche: {query}"


def get_tools_list():
    return [ingest_documents, search_documents]
