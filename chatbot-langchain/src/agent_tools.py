from langchain_core.tools import tool
import requests
import os

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp-server:8001")

@tool
def ingest_documents() -> str:
    """Lance l'ingestion, la classification et l'indexation de tous les PDF présents dans data/."""
    print("\n[MCP CLIENT] Demande d'ingestion au serveur MCP...")
    try:
        # Si votre serveur MCP expose un endpoint HTTP/FastAPI
        response = requests.post(f"{MCP_SERVER_URL}/ingest")
        return response.text
    except Exception as e:
        return f"Erreur de communication avec le serveur MCP : {str(e)}"

@tool
def search_cv(query: str) -> str:
    """Recherche des informations techniques ou du contenu spécifiquement dans le CV."""
    print(f"\n[MCP CLIENT] Appel de search_cv('{query}')")
    # Simulation ou appel HTTP vers le MCP
    return "Résultat de la recherche CV récupéré via MCP."

@tool
def search_devis(query: str) -> str:
    """Recherche des informations ou clauses spécifiquement dans les devis."""
    print(f"\n[MCP CLIENT] Appel de search_devis('{query}')")
    return "Résultat de la recherche devis récupéré via MCP."

@tool
def search_global(query: str) -> str:
    """Effectue une recherche globale à travers tous les documents disponibles."""
    print(f"\n[MCP CLIENT] Appel de search_global('{query}')")
    return "Résultat de la recherche globale récupéré via MCP."

def get_tools_list():
    return [ingest_documents, search_cv, search_devis, search_global]