import os
from langchain_ollama import ChatOllama
from agent_tools import get_tools_list

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")


def init_llm_with_tools():
    """Initialise Ollama et lui associe les outils disponibles. Retourne (llm_with_tools, llm_base, tools)."""
    print(f"Connexion à Ollama sur {OLLAMA_BASE_URL} avec le modèle {MODEL_NAME}...")

    llm = ChatOllama(model=MODEL_NAME, base_url=OLLAMA_BASE_URL, temperature=0.1)
    tools = get_tools_list()
    return llm.bind_tools(tools), llm, tools
