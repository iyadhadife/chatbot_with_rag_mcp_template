import sys
import logging
from mcp.server.fastmcp import FastMCP
from src.rag_engine.retriever import query_rag
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount, Route
import uvicorn

# Configuration des logs (Toujours utile)
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

if __name__ == "__main__":
    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.routing import Mount

    # 1. Configuration CORS pour que l'Inspecteur (et tout le monde) puisse se connecter
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Autorise toutes les origines
            allow_methods=["GET", "POST", "OPTIONS"],  # Autorise les vérifications
            allow_headers=["*"],
        )
    ]

    # 2. LA CORRECTION EST ICI : 
    # On monte l'app FastMCP à la racine "/" et non pas sur "/sse"
    # Comme ça, l'adresse finale reste "http://localhost:8000/sse"
    # (car FastMCP ajoute lui-même son propre suffixe /sse)
    app = Starlette(routes=[Mount("/", mcp.sse_app())], middleware=middleware)

    print("🔓 Serveur RAG prêt sur http://0.0.0.0:8000/sse (CORS activé)")
    
    # 3. Lancement
    uvicorn.run(app, port=8000, host="0.0.0.0")