import json
import os
import urllib.request
from functools import lru_cache

from langchain_ollama import ChatOllama
from agent_tools import get_tools_list

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
DEFAULT_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
# Fenêtre de contexte explicite (le défaut d'Ollama, 2048-4096, tronque silencieusement)
NUM_CTX         = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

_TOOLS = get_tools_list()


@lru_cache(maxsize=8)
def get_llms(model_name: str):
    """
    Retourne (llm_with_tools, llm_base) pour le modèle Ollama demandé.
    Mis en cache par nom de modèle (évite de reconstruire à chaque requête).
    """
    llm = ChatOllama(model=model_name, base_url=OLLAMA_BASE_URL, temperature=0.1, num_ctx=NUM_CTX)
    return llm.bind_tools(_TOOLS), llm


def list_ollama_models() -> list[str]:
    """
    Liste les modèles installés localement via l'API Ollama (GET /api/tags).
    Retourne une liste triée de noms (ex: ["llama3.2:3b", "qwen2.5:0.5b"]).
    Lève une exception si Ollama est injoignable (gérée par l'appelant).
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    return sorted(models)


def init_llm_with_tools():
    """Compat : initialise le modèle par défaut. Retourne (llm_with_tools, llm_base, tools)."""
    llm_with_tools, llm_base = get_llms(DEFAULT_MODEL)
    return llm_with_tools, llm_base, _TOOLS
