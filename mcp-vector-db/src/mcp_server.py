from mcp.server.fastmcp import FastMCP
import os

from rag_pipeline.ingest import ingest_pdfs
from rag_pipeline.retriever import ChatbotRetriever

mcp = FastMCP("Professional-Document-MCP-Server")
retriever = ChatbotRetriever()


@mcp.tool()
def ingest_documents() -> str:
    """
    Lance l'ingestion, la classification et l'indexation des documents PDF.
    Les CVs sont découpés par sections sémantiques (Compétences, Expériences…).
    Les autres documents sont découpés par paragraphes avec numéros de page.
    Chaque chunk embarque des métadonnées riches et des liens vers les chunks voisins.
    """
    try:
        ingest_pdfs()
        return "Ingestion et indexation des documents réalisées avec succès."
    except Exception as e:
        return f"Erreur lors de l'ingestion : {str(e)}"


@mcp.tool()
def search_cv(query: str) -> str:
    """
    Recherche des informations dans les CVs (toutes sections confondues).
    Utilise un filtre doc_type=CV pour ne chercher que dans les CV.
    """
    try:
        return retriever.get_context_by_filter(query, doc_type="CV", n_results=4)
    except Exception as e:
        return f"Erreur CV : {str(e)}"


@mcp.tool()
def search_cv_skills(query: str) -> str:
    """
    Recherche spécifiquement dans les sections de compétences des CVs.
    Idéal pour trouver les technologies, langages et outils maîtrisés par un candidat.
    """
    try:
        return retriever.get_context_by_filter(
            query, doc_type="CV", section_type="COMPETENCES", n_results=4
        )
    except Exception as e:
        return f"Erreur recherche compétences : {str(e)}"


@mcp.tool()
def search_devis(query: str) -> str:
    """
    Recherche des informations ou clauses spécifiquement dans les devis.
    Utilise un filtre doc_type=DEVIS.
    """
    try:
        return retriever.get_context_by_filter(query, doc_type="DEVIS", n_results=4)
    except Exception as e:
        return f"Erreur lors de la recherche dans le devis : {str(e)}"


@mcp.tool()
def search_global(query: str) -> str:
    """
    Effectue une recherche sémantique globale à travers tous les documents disponibles.
    Retourne les 6 chunks les plus pertinents, tous types confondus.
    """
    try:
        return retriever.get_context(query, n_results=6)
    except Exception as e:
        return f"Erreur lors de la recherche globale : {str(e)}"


@mcp.tool()
def get_linked_context(chunk_id: str) -> str:
    """
    Récupère un chunk et ses voisins (précédent et suivant) à partir de son identifiant.
    Utile pour obtenir plus de contexte autour d'un résultat de recherche.
    Exemple d'identifiant : 'CV_Ingenieur_IA.pdf_section_2'
    """
    try:
        return retriever.get_linked_chunks(chunk_id)
    except Exception as e:
        return f"Erreur lors de la récupération du contexte lié : {str(e)}"


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8001
    mcp.run(transport="sse")
