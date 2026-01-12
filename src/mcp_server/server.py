from mcp.server.fastmcp import FastMCP
from src.rag_engine.retriever import query_rag

# Initialisation du serveur MCP
mcp = FastMCP("MonRAGChatbot")

@mcp.tool()
def interroger_base_connaissance(question: str) -> str:
    """
    Utilise cet outil pour répondre aux questions basées sur les documents internes.
    Args:
        question: La question de l'utilisateur.
    """
    contexte = query_rag(question)
    
    if not contexte:
        return "Aucune information trouvée dans la base de connaissances."
        
    return "\n\n".join(contexte)

if __name__ == "__main__":
    mcp.run()