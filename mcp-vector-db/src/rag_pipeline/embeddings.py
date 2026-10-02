"""
Embeddings multilingues (très bons en français) via Ollama.

Les vecteurs sont calculés ici et passés explicitement à ChromaDB
(`embeddings=` / `query_embeddings=`) : pas de dépendance à l'API
d'embedding-function de Chroma, qui varie selon les versions.

Prérequis côté hôte : `ollama pull bge-m3`
"""
import os

import ollama

OLLAMA_URL      = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
_BATCH          = 16

_client = None


def embed_texts(texts: list[str]) -> list[list[float]]:
    global _client
    if _client is None:
        _client = ollama.Client(host=OLLAMA_URL)
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        try:
            res = _client.embed(model=EMBEDDING_MODEL, input=texts[i:i + _BATCH])
        except ollama.ResponseError as e:
            if e.status_code == 404:
                raise RuntimeError(
                    f"Modèle d'embedding '{EMBEDDING_MODEL}' introuvable dans Ollama : "
                    f"lancez `ollama pull {EMBEDDING_MODEL}` sur l'hôte."
                ) from e
            raise
        vectors.extend(res["embeddings"])
    return vectors
