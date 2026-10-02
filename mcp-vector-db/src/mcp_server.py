from mcp.server.fastmcp import FastMCP
import base64
import json
import os
import re
from pathlib import Path

from rag_pipeline.ingest import ingest_pdfs
from rag_pipeline.retriever import ChatbotRetriever

PDF_DIR = "./data/pdfs"

mcp = FastMCP("Professional-Document-MCP-Server")
retriever = ChatbotRetriever()


@mcp.tool()
def ingest_documents() -> str:
    """
    Réindexation COMPLÈTE : supprime toute la base existante puis indexe tous
    les PDF présents dans data/pdfs.
    Chaque document est découpé en chunks de taille fixe avec recouvrement,
    enrichis de métadonnées (type, mots-clés, résumé) puis indexés dans ChromaDB.
    """
    try:
        n = ingest_pdfs(PDF_DIR, reset=True)
        return f"Base réinitialisée, {n} document(s) indexé(s)."
    except Exception as e:
        return f"Erreur lors de l'ingestion : {str(e)}"


@mcp.tool()
def add_document(filename: str, content_base64: str) -> str:
    """
    Ajoute un PDF (contenu encodé en base64) à data/pdfs et l'indexe, sans
    toucher aux documents déjà indexés.
    """
    try:
        name = re.sub(r"[^\w.\- ]", "_", Path(filename).name)
        if not name.lower().endswith(".pdf"):
            return f"Refusé : '{filename}' n'est pas un PDF."
        os.makedirs(PDF_DIR, exist_ok=True)
        Path(PDF_DIR, name).write_bytes(base64.b64decode(content_base64))
        n = ingest_pdfs(PDF_DIR, reset=False, only=[name])
        return f"{name} ajouté et indexé." if n else f"{name} : aucun texte exploitable."
    except Exception as e:
        return f"Erreur lors de l'ajout : {str(e)}"


@mcp.tool()
def search_documents(query: str) -> str:
    """
    Recherche sémantique dans TOUTE la base documentaire (CV, devis, factures,
    contrats…). Unique outil de recherche : renvoie les passages les plus
    pertinents, tous documents confondus. Les résultats trop éloignés de la
    question sont automatiquement filtrés (seuil de distance).
    """
    try:
        return retriever.get_context(query, n_results=8)
    except Exception as e:
        return f"Erreur lors de la recherche : {str(e)}"


# ── Utilitaire (hors agent) : inventaire pour l'onglet d'inspection ───────────

@mcp.tool()
def list_indexed_chunks() -> str:
    """
    Retourne, au format JSON, l'inventaire complet des chunks indexés dans
    ChromaDB, groupés par document, avec leurs métadonnées. Destiné à l'onglet
    d'inspection de l'interface (pas à la recherche conversationnelle).
    """
    try:
        return json.dumps(retriever.list_all_chunks(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"total": 0, "documents": [], "error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8001
    mcp.run(transport="sse")
