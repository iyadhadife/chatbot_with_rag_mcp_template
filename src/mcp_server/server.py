import sys
import logging
import uvicorn
from mcp.server.fastmcp import FastMCP
from src.rag_engine.retriever import query_rag
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

#Running command
#uvicorn src.mcp_server.server:app --host localhost  --port 8000

# Configuration des logs
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = FastMCP("MonRAGChatbot")

@mcp.tool()
def interroger_base_connaissance(question: str) -> str:
    logging.info(f"Question reçue : {question}")
    try:
        contexte = query_rag(question)
        if not contexte:
            return "Aucune information trouvée."
        return "\n".join([str(doc) for doc in contexte])
    except Exception as e:
        return f"Erreur : {str(e)}"

# --- CONFIGURATION STARLETTE (Déplacée ici pour être visible par Uvicorn) ---

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
]

# Cette variable est maintenant au "top-level" du module
app = Starlette(routes=[Mount("/", mcp.sse_app())], middleware=middleware)

# --- BLOC D'EXÉCUTION DIRECTE ---
if __name__ == "__main__":
    print("🔓 Serveur RAG prêt sur http://0.0.0.0:8000/sse (CORS activé)")
    uvicorn.run("src.mcp_server.server:app", port=8000, host="0.0.0.0", reload=True)