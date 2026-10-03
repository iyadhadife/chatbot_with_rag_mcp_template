"""
Orchestrateur d'ingestion PDF.

Pipeline (100 % CPU, sans LLM par défaut) :
  1. Extraction texte page par page (pypdf)
  2. Calcul document_id (MD5) — déduplication et traçabilité
  3. Classification du type de document (règles de vocabulaire, sans LLM)
  4. Déduplication : suppression des anciens chunks si le document existe déjà
  5. Découpage à taille fixe avec overlap (chunker unique, tous types confondus)
  6. Génération de métadonnées (YAKE + TextRank + regex ; sans LLM par défaut)
  7. Insertion dans ChromaDB
"""
import glob
import hashlib
import logging
import os
from pathlib import Path

import chromadb
from pypdf import PdfReader

from rag_pipeline.chunker import chunk_documents
from rag_pipeline.doc_profile import generate_document_profile
from rag_pipeline.embeddings import EMBEDDING_MODEL, embed_texts
from rag_pipeline.text_analysis import classify_document_type
from rag_pipeline.metadata_generator import (
    MetadataGenerator,
    flatten_for_chroma,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))


# ── Extraction PDF ────────────────────────────────────────────────────────────

def extract_text_per_page(pdf_path: str) -> list[tuple[int, str]]:
    """Extrait le texte page par page → [(page_num, texte), ...]."""
    try:
        reader = PdfReader(pdf_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append((i + 1, text.strip()))
        return pages
    except Exception as e:
        logger.error(f"Erreur lecture {pdf_path}: {e}")
        return []


# ── Identifiant document ──────────────────────────────────────────────────────

def compute_document_id(full_text: str, filename: str) -> str:
    """
    Identifiant stable : MD5 du contenu textuel (12 hex chars).
    Permet la déduplication et le lien chunk → document.
    """
    payload = f"{filename}::{full_text}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]


# Note : la classification est assurée par
# rag_pipeline.text_analysis.classify_document_type (règles de vocabulaire,
# sans LLM). Le découpage est assuré par rag_pipeline.chunker.chunk_documents.


# ── Déduplication ─────────────────────────────────────────────────────────────

def _delete_existing_document(collection, document_id: str, filename: str) -> int:
    """
    Supprime tous les chunks existants pour ce document (par document_id).
    Retourne le nombre de chunks supprimés.
    """
    try:
        existing = collection.get(
            where={"document_id": {"$eq": document_id}},
            include=[],
        )
        ids_to_delete = existing.get("ids", [])
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            logger.info(f"  ↩ {len(ids_to_delete)} anciens chunks supprimés (re-ingestion de {filename})")
            return len(ids_to_delete)
    except Exception as e:
        logger.warning(f"  ⚠ Impossible de vérifier les doublons : {e}")
    return 0


def _delete_by_source(collection, filename: str) -> None:
    """Supprime tout ce qui provient d'un même nom de fichier (ancienne version)."""
    try:
        old = collection.get(where={"source": {"$eq": filename}}, include=[])
        if old.get("ids"):
            collection.delete(ids=old["ids"])
    except Exception as e:
        logger.warning(f"  ⚠ Nettoyage par source impossible : {e}")


# ── Pipeline principal ────────────────────────────────────────────────────────

COLLECTION_NAME = "pdf_rag_collection"
DOCS_COLLECTION_NAME = "pdf_documents"  # 1 vecteur par document (profil LLM)
_COSINE = {"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL}


def _reset_collection(client, name: str = COLLECTION_NAME):
    """Supprime toute la base existante et recrée une collection cosine vide."""
    if name == COLLECTION_NAME:  # la base = chunks + profils de documents
        _reset_collection(client, DOCS_COLLECTION_NAME)
    try:
        client.delete_collection(name=name)
        logger.info("Base existante supprimée.")
    except Exception:
        pass  # collection inexistante
    return client.create_collection(name=name, metadata=_COSINE)


def _get_cosine_collection(client, name: str = COLLECTION_NAME):
    """Collection en distance cosine ; recréée si elle existe avec une autre métrique."""
    try:
        col = client.get_collection(name=name)
        meta = col.metadata or {}
        if (meta.get("hnsw:space") != "cosine"
                or meta.get("embedding_model") != EMBEDDING_MODEL):
            logger.warning("Collection créée avec un autre modèle d'embedding → "
                           "recréation (réindexez tous les PDF).")
            return _reset_collection(client, name)
        return col
    except Exception:
        return client.get_or_create_collection(name=name, metadata=_COSINE)


def ingest_pdfs(pdf_dir: str = "./data/pdfs", reset: bool = True,
                only: list[str] | None = None) -> int:
    """
    Indexe les PDF de `pdf_dir`.
      - reset=True  : supprime toute la base avant (réindexation complète).
      - reset=False : ajoute sans toucher à l'existant (un document déjà
                      indexé est remplacé grâce à la déduplication).
      - only        : liste de noms de fichiers à traiter (sinon tous).
    Retourne le nombre de PDF indexés.
    """
    client     = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = _reset_collection(client) if reset else _get_cosine_collection(client)
    docs_collection = _get_cosine_collection(client, DOCS_COLLECTION_NAME)
    generator  = MetadataGenerator()

    pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))
    if only is not None:
        wanted = set(only)
        pdf_files = [p for p in pdf_files if Path(p).name in wanted]
    if not pdf_files:
        logger.info(f"Aucun PDF à indexer dans {pdf_dir}.")
        return 0

    indexed = 0

    for pdf_path in pdf_files:
        filename = Path(pdf_path).name
        logger.info(f"\nTraitement : {filename}")

        pages = extract_text_per_page(pdf_path)
        if not pages:
            logger.warning("  → Document vide ou illisible.")
            continue

        full_text   = "\n".join(text for _, text in pages)
        document_id = compute_document_id(full_text, filename)

        # Déduplication : par contenu (document_id) ET par nom de fichier
        # (un PDF modifié a un nouvel id, ses anciens chunks doivent partir).
        for col in (collection, docs_collection):
            _delete_existing_document(col, document_id, filename)
            _delete_by_source(col, filename)

        # Classification (sans LLM) — sert uniquement de métadonnée doc_type
        doc_type = classify_document_type(full_text)
        logger.info(f"  → Type détecté : {doc_type} | document_id : {document_id}")

        # Découpage à taille fixe avec overlap (chunker unique)
        documents, metadatas, ids = chunk_documents(pages, filename, doc_type)
        if not documents:
            logger.warning("  → Aucun chunk généré.")
            continue

        # ── Métadonnées document (sans LLM : YAKE + TextRank + regex) ─────────
        doc_meta = generator.generate_document_metadata(full_text, filename, doc_type)
        doc_meta_flat = flatten_for_chroma(doc_meta)
        logger.info(f"  → Métadonnées document : {doc_meta.title or filename} | {doc_meta.summary[:80]}…")

        # ── Profil du document par LLM (objectif, caractéristiques, sujet) ────
        profile = generate_document_profile(
            generator, full_text, filename,
            fallback_title=doc_meta.title, fallback_summary=doc_meta.summary,
            doc_type=doc_type,
        )
        logger.info(f"  → Profil : {profile.document_kind} | sujet : {profile.subject} | "
                    f"objectif : {profile.objective[:80]}")

        # ── Enrichissement de chaque chunk ───────────────────────────────────
        enriched_metadatas = []
        for i, (doc_text, meta) in enumerate(zip(documents, metadatas)):
            section_name = meta.get("section_name", f"chunk_{i}")
            chunk_meta = generator.generate_chunk_metadata(doc_text, section_name, doc_meta.title)
            chunk_meta_flat = flatten_for_chroma(chunk_meta)

            # Fusion : doc_meta < chunk_meta < meta chunker ; document_id/doc_title prioritaires
            merged = {
                **doc_meta_flat,
                **chunk_meta_flat,
                **meta,
                "document_id": document_id,
                "doc_title":   profile.title or doc_meta.title or filename,
                "doc_subject": profile.subject,
                "doc_objective": profile.objective,
            }
            enriched_metadatas.append(merged)

        # ── Insertion ChromaDB ────────────────────────────────────────────────
        collection.add(documents=documents, ids=ids, metadatas=enriched_metadatas,
                       embeddings=embed_texts(documents))

        profile_text = profile.to_text()
        docs_collection.add(
            ids=[document_id],
            documents=[profile_text],
            embeddings=embed_texts([profile_text]),
            metadatas=[{
                **profile.to_chroma(),
                "document_id": document_id,
                "source":      filename,
                "doc_type":    doc_type,
                "chunk_count": len(documents),
            }],
        )
        logger.info(f"  → {len(documents)} chunks insérés [{doc_type}]")
        indexed += 1

    return indexed


if __name__ == "__main__":
    os.makedirs("./data/pdfs", exist_ok=True)
    ingest_pdfs()
