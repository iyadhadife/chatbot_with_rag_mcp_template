import os
from langchain_ollama import ChatOllama
from agent_tools import get_tools_list

def init_llm_with_tools():
    """Initialise Ollama et lui associe automatiquement les outils disponibles."""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    print(f"Connexion à Ollama sur {ollama_base_url} avec liaison des outils (Tools)...")
    
    llm = ChatOllama(
        model="qwen2.5:7b",
        base_url=ollama_base_url,
        temperature=0.1
    )
    
    # On lie les outils au modèle pour l'activer en mode Agent / Tool Use
    tools = get_tools_list()
    return llm.bind_tools(tools), tools