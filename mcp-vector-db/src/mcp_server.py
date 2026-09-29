from mcp.server.fastmcp import FastMCP
import os

# Importation de vos scripts existants (ajustez les noms des fonctions selon vos fichiers)
from rag_pipeline.ingest import ingest_pdfs  # Remplacez par le nom de votre fonction d'ingestion principale
from rag_pipeline.retriever import ChatbotRetriever  # Votre classe ou vos fonctions de recherche

# Initialisation du serveur MCP
mcp = FastMCP("Professional-Document-MCP-Server")

# Instanciation de votre retriever existant
retriever = ChatbotRetriever()

@mcp.tool()
def ingest_documents() -> str:
    """Lance l'ingestion, la classification et l'indexation des documents PDF."""
    try:
        # Appel direct de votre code d'ingestion existant
        ingest_pdfs()
        return "Ingestion et indexation des documents réalisées avec succès."
    except Exception as e:
        return f"Erreur lors de l'ingestion : {str(e)}"

@mcp.tool()
def search_cv(query: str) -> str:
    """Recherche des informations dans le CV."""
    try:
        # Si votre retriever utilise get_context avec un filtre metadata :
        return retriever.get_context(query, n_results=4) # ou filtre selon votre implémentation
    except Exception as e:
        return f"Erreur CV : {str(e)}"

@mcp.tool()
def search_devis(query: str) -> str:
    """Recherche des informations ou clauses spécifiquement dans les devis."""
    try:
        # Appel de votre retriever avec filtrage sur le Devis
        return retriever.get_context_by_filter(query, doc_type="DEVIS")
    except Exception as e:
        return f"Erreur lors de la recherche dans le devis : {str(e)}"

@mcp.tool()
def search_global(query: str) -> str:
    """Effectue une recherche globale à travers tous les documents disponibles."""
    try:
        # Appel de votre retriever en mode transversal
        return retriever.get_context(query, n_results=6)
    except Exception as e:
        return f"Erreur lors de la recherche globale : {str(e)}"

if __name__ == "__main__":
    # Configuration explicite pour écouter sur le réseau Docker (port 8001)
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8001
    mcp.run(transport="sse")