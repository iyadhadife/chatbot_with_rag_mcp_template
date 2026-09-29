import os
import chromadb

# Récupération des variables d'environnement définies dans le docker-compose
CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

class ChatbotRetriever:
    def __init__(self, collection_name="pdf_rag_collection"):
        """Initialise la connexion HTTP avec le conteneur ChromaDB."""
        try:
            self.client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            self.collection = self.client.get_or_create_collection(name=collection_name)
        except Exception as e:
            print(f"Erreur lors de la connexion à ChromaDB : {e}")

    def get_context(self, query: str, n_results: int = 3) -> str:
        """
        Interroge ChromaDB pour trouver les chunks les plus proches de la question,
        puis retourne un texte formaté contenant les sources et les extraits.
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            
            if not documents:
                return "Aucun document pertinent trouvé dans la base de données."

            context_blocks = []
            for doc, meta in zip(documents, metadatas):
                source = meta.get("source", "Inconnu")
                doc_type = meta.get("doc_type", "DOCUMENT")
                
                # Formatage explicite pour que le LLM sache exactement d'où ça vient
                context_blocks.append(f"--- [TYPE: {doc_type} | SOURCE: {source}] ---\n{doc}")
                
            return "\n\n".join(context_blocks)
            
        except Exception as e:
            print(f"Erreur lors de la recherche dans ChromaDB : {e}")
            return "Erreur lors de la récupération du contexte."