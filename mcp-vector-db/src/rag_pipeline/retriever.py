import os
import chromadb

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))


class ChatbotRetriever:
    def __init__(self, collection_name: str = "pdf_rag_collection"):
        try:
            self.client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            self.collection = self.client.get_or_create_collection(name=collection_name)
        except Exception as e:
            print(f"Erreur lors de la connexion à ChromaDB : {e}")

    def _format_results(self, results: dict) -> str:
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not documents:
            return "Aucun document pertinent trouvé dans la base de données."

        blocks = []
        for doc, meta in zip(documents, metadatas):
            source = meta.get("source", "Inconnu")
            doc_type = meta.get("doc_type", "DOCUMENT")
            section_type = meta.get("section_type", "")
            section_name = meta.get("section_name", "")
            skills = meta.get("skills", "")
            page = meta.get("page_number", "")

            parts = [f"TYPE: {doc_type}", f"SOURCE: {source}"]
            if section_type:
                parts.append(f"SECTION: {section_type}")
            if section_name and section_name != section_type:
                parts.append(f"TITRE: {section_name}")
            if page:
                parts.append(f"PAGE: {page}")

            block = f"--- [{' | '.join(parts)}] ---\n{doc}"
            if skills:
                block += f"\n[Compétences détectées: {skills}]"
            blocks.append(block)

        return "\n\n".join(blocks)

    def get_context(self, query: str, n_results: int = 3) -> str:
        """Recherche sémantique globale sans filtre."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas"],
            )
            return self._format_results(results)
        except Exception as e:
            print(f"Erreur lors de la recherche dans ChromaDB : {e}")
            return "Erreur lors de la récupération du contexte."

    def get_context_by_filter(
        self,
        query: str,
        doc_type: str = None,
        section_type: str = None,
        n_results: int = 4,
    ) -> str:
        """
        Recherche sémantique avec filtrage sur doc_type et/ou section_type.
        Permet de cibler un type de document (CV, DEVIS…) ou une section (COMPETENCES…).
        """
        try:
            conditions = []
            if doc_type:
                conditions.append({"doc_type": {"$eq": doc_type}})
            if section_type:
                conditions.append({"section_type": {"$eq": section_type}})

            if len(conditions) > 1:
                where = {"$and": conditions}
            elif len(conditions) == 1:
                where = conditions[0]
            else:
                where = None

            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas"],
            )
            return self._format_results(results)
        except Exception as e:
            print(f"Erreur lors de la recherche filtrée dans ChromaDB : {e}")
            return "Erreur lors de la récupération du contexte filtré."

    def get_linked_chunks(self, chunk_id: str) -> str:
        """
        Récupère un chunk et ses voisins (précédent / suivant) grâce aux liens
        prev_chunk_id / next_chunk_id stockés dans les métadonnées.
        Utile pour fournir plus de contexte autour d'un résultat pertinent.
        """
        try:
            result = self.collection.get(
                ids=[chunk_id], include=["documents", "metadatas"]
            )
            if not result["documents"]:
                return f"Chunk '{chunk_id}' introuvable."

            doc = result["documents"][0]
            meta = result["metadatas"][0]
            blocks = [f"[Chunk principal: {chunk_id}]\n{doc}"]

            for key, label in [("prev_chunk_id", "Précédent"), ("next_chunk_id", "Suivant")]:
                neighbor_id = meta.get(key, "")
                if not neighbor_id:
                    continue
                try:
                    n = self.collection.get(ids=[neighbor_id], include=["documents"])
                    if n["documents"]:
                        blocks.append(f"[Chunk {label}: {neighbor_id}]\n{n['documents'][0]}")
                except Exception:
                    pass

            return "\n\n".join(blocks)
        except Exception as e:
            return f"Erreur lors de la récupération du chunk lié : {e}"
