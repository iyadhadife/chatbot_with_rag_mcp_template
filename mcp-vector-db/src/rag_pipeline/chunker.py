"""
Découpage à taille fixe avec recouvrement (overlap).

Approche unique pour TOUS les types de documents : au lieu d'un découpage
sémantique par sections, on produit des chunks de taille fixe qui se
chevauchent. Cela garantit qu'une idée répartie sur une frontière n'est jamais
perdue (le recouvrement la fait apparaître dans deux chunks consécutifs).

Paramètres (variables d'environnement) :
  CHUNK_SIZE     — taille cible d'un chunk, en caractères (défaut : 800)
  CHUNK_OVERLAP  — recouvrement entre deux chunks consécutifs (défaut : 200)

Note : la taille est mesurée en CARACTÈRES. ~800 caractères ≈ 200 tokens.
Pour viser ~800 tokens, passez CHUNK_SIZE≈3200 et CHUNK_OVERLAP≈800.

Le découpage est « boundary-aware » : on évite de couper au milieu d'un mot en
reculant jusqu'au dernier saut de ligne ou espace disponible.
"""
import logging
import os

logger = logging.getLogger(__name__)

CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))


def _chunk_text(text: str, size: int, overlap: int) -> list[tuple[str, int]]:
    """
    Découpe `text` en fenêtres de ~`size` caractères avec `overlap` de
    recouvrement. Retourne une liste de (texte_du_chunk, offset_de_début).
    On recule la coupe jusqu'à une frontière (\\n ou espace) pour ne pas
    couper un mot en deux.
    """
    text = text.strip()
    n = len(text)
    if n == 0:
        return []
    if n <= size:
        return [(text, 0)]

    # Garde-fous : overlap strictement inférieur à size pour garantir la progression.
    overlap = max(0, min(overlap, size - 1))
    min_cut = int(size * 0.6)  # ne pas reculer la coupe trop loin

    chunks: list[tuple[str, int]] = []
    start = 0
    while start < n:
        end = min(start + size, n)

        # Recul vers une frontière propre (sauf pour le dernier chunk).
        if end < n:
            boundary = text.rfind("\n", start + min_cut, end)
            if boundary == -1:
                boundary = text.rfind(" ", start + min_cut, end)
            if boundary != -1 and boundary > start:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start))

        if end >= n:
            break
        start = max(end - overlap, start + 1)

    return chunks


def _build_page_spans(pages: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int, int]]]:
    """
    Concatène les pages et retourne (full_text, spans) où chaque span est
    (offset_début, offset_fin, numéro_de_page) dans full_text.
    """
    parts, spans, pos = [], [], 0
    for page_num, txt in pages:
        parts.append(txt)
        spans.append((pos, pos + len(txt), page_num))
        pos += len(txt) + 1  # +1 pour le "\n" de jonction
    return "\n".join(parts), spans


def _page_for_offset(offset: int, spans: list[tuple[int, int, int]]) -> int:
    for start, end, page_num in spans:
        if start <= offset < end:
            return page_num
    return spans[-1][2] if spans else 1


def chunk_documents(
    pages: list[tuple[int, str]],
    filename: str,
    doc_type: str,
    size: int = None,
    overlap: int = None,
) -> tuple[list[str], list[dict], list[str]]:
    """
    Découpe un document (liste de pages) en chunks à taille fixe avec overlap.
    Retourne (documents, metadatas, ids) prêts pour ChromaDB.
    """
    size    = size if size is not None else CHUNK_SIZE
    overlap = overlap if overlap is not None else CHUNK_OVERLAP

    full_text, spans = _build_page_spans(pages)
    raw_chunks = _chunk_text(full_text, size, overlap)

    documents, metadatas, ids = [], [], []
    total = len(raw_chunks)

    for i, (chunk_text, offset) in enumerate(raw_chunks):
        chunk_id = f"{filename}_chunk_{i}"
        documents.append(chunk_text)
        metadatas.append({
            "source":        filename,
            "doc_type":      doc_type,
            "chunk_index":   i,
            "total_chunks":  total,
            "section_type":  "CHUNK",
            "section_name":  f"Chunk {i + 1}/{total}",
            "page_number":   _page_for_offset(offset, spans),
            "char_count":    len(chunk_text),
            "prev_chunk_id": f"{filename}_chunk_{i - 1}" if i > 0 else "",
            "next_chunk_id": f"{filename}_chunk_{i + 1}" if i < total - 1 else "",
        })
        ids.append(chunk_id)

    logger.info(f"  → {total} chunks (taille={size}, overlap={overlap} car.)")
    return documents, metadatas, ids
