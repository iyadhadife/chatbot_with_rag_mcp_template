import os
import glob
import re
from pathlib import Path
import chromadb
from pypdf import PdfReader
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

# Patterns de détection des sections pour les CVs (français et anglais)
CV_SECTION_PATTERNS = [
    (r"(?i)^(COMPÉTENCES?|SKILLS?|TECHNICAL\s+SKILLS?|HARD\s+SKILLS?|SOFT\s+SKILLS?|STACK\s+TECHNIQUE|OUTILS?\s+ET\s+TECHNOLOGIES?)", "COMPETENCES"),
    (r"(?i)^(EXPÉRIENCES?\s+PROFESSIONNELLES?|EXPÉRIENCES?|WORK\s+EXPERIENCE|PROFESSIONAL\s+EXPERIENCE|PARCOURS\s+PROFESSIONNEL)", "EXPERIENCES"),
    (r"(?i)^(FORMATION|ÉDUCATION|EDUCATION|DIPLÔMES?|CURSUS|STUDIES|ACADEMIC\s+BACKGROUND)", "FORMATION"),
    (r"(?i)^(LANGUES?|LANGUAGES?)", "LANGUES"),
    (r"(?i)^(PROJETS?\s+PERSONNELS?|PROJETS?|PROJECTS?|RÉALISATIONS?|PORTFOLIO)", "PROJETS"),
    (r"(?i)^(CERTIFICATIONS?|CERTIFIATS?|ACCRÉDITATIONS?)", "CERTIFICATIONS"),
    (r"(?i)^(PROFIL|RÉSUMÉ\s+PROFESSIONNEL|RÉSUMÉ|SUMMARY|ABOUT\s+ME|À\s+PROPOS|OBJECTIF)", "PROFIL"),
    (r"(?i)^(LOISIRS?|CENTRES?\s+D.INTÉRÊT|HOBBIES?|INTERESTS?|ACTIVITÉS?)", "LOISIRS"),
    (r"(?i)^(INFORMATIONS?\s+PERSONNELLES?|COORDONNÉES?|CONTACT)", "CONTACT"),
]


def extract_text_per_page(pdf_path: str) -> list[tuple[int, str]]:
    """Extrait le texte page par page, retourne [(page_num, texte), ...]."""
    try:
        reader = PdfReader(pdf_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append((i + 1, text.strip()))
        return pages
    except Exception as e:
        print(f"Erreur lecture {pdf_path}: {e}")
        return []


def classify_document_type(text_sample: str) -> str:
    """Classifie le type de document via le LLM local."""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    llm = ChatOllama(model=model_name, base_url=ollama_base_url, temperature=0.0)

    prompt = [
        SystemMessage(
            content=(
                "Tu es un classificateur de documents professionnels. "
                "Réponds UNIQUEMENT par un mot clé court en majuscules "
                "(ex: CV, DEVIS, FACTURE, CONTRAT, RAPPORT, AUTRE) "
                "qui qualifie le document fourni."
            )
        ),
        HumanMessage(content=f"Voici le début du document :\n\n{text_sample[:1500]}"),
    ]

    try:
        response = llm.invoke(prompt)
        doc_type = response.content.strip().upper()
        doc_type = "".join(c for c in doc_type if c.isalnum() or c == "_")
        return doc_type if doc_type else "INCONNU"
    except Exception as e:
        print(f"Erreur classification IA : {e}")
        return "INCONNU"


def _detect_cv_section(line: str) -> str | None:
    """Retourne le type de section si la ligne est un en-tête de section CV, sinon None."""
    line = line.strip()
    if not line or len(line) > 80:
        return None
    for pattern, section_type in CV_SECTION_PATTERNS:
        if re.match(pattern, line):
            return section_type
    return None


def _split_into_sections(full_text: str) -> list[tuple[str, str, str]]:
    """
    Découpe le texte en sections sémantiques.
    Retourne [(section_name, section_type, section_text), ...].
    """
    lines = full_text.split("\n")
    sections = []
    current_name = "ENTETE"
    current_type = "ENTETE"
    current_lines: list[str] = []

    for line in lines:
        section_type = _detect_cv_section(line)
        if section_type is not None:
            if current_lines:
                sections.append((current_name, current_type, "\n".join(current_lines)))
            current_name = line.strip()
            current_type = section_type
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_name, current_type, "\n".join(current_lines)))

    return sections


def _extract_skills_from_text(text: str) -> list[str]:
    """Extrait une liste de compétences depuis une section COMPETENCES."""
    raw = re.split(r"[\n,•\-\*·|/]", text)
    skills = []
    for item in raw:
        item = item.strip()
        # Les compétences sont courtes (2–6 mots) et ne finissent pas par un point
        if 2 < len(item) < 60 and not item.endswith("."):
            skills.append(item)
    return skills[:40]


def chunk_cv(
    pages: list[tuple[int, str]], filename: str, doc_type: str
) -> tuple[list[str], list[dict], list[str]]:
    """
    Chunking sémantique pour les CVs : un chunk par section.
    Chaque chunk est lié au précédent et au suivant via prev_chunk_id / next_chunk_id.
    """
    full_text = "\n".join(text for _, text in pages)
    sections = _split_into_sections(full_text)

    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    valid_sections = [(n, t, txt) for n, t, txt in sections if txt.strip()]
    total = len(valid_sections)

    for i, (section_name, section_type, section_text) in enumerate(valid_sections):
        chunk_id = f"{filename}_section_{i}"
        prev_id = f"{filename}_section_{i - 1}" if i > 0 else ""
        next_id = f"{filename}_section_{i + 1}" if i < total - 1 else ""

        skills = _extract_skills_from_text(section_text) if section_type == "COMPETENCES" else []

        metadata = {
            "source": filename,
            "doc_type": doc_type,
            "chunk_index": i,
            "total_chunks": total,
            "section_name": section_name,
            "section_type": section_type,
            "skills": ", ".join(skills),
            "prev_chunk_id": prev_id,
            "next_chunk_id": next_id,
        }

        documents.append(f"[SECTION: {section_name}]\n{section_text}")
        metadatas.append(metadata)
        ids.append(chunk_id)

    return documents, metadatas, ids


def chunk_by_paragraphs(
    pages: list[tuple[int, str]],
    filename: str,
    doc_type: str,
    max_chunk_size: int = 800,
) -> tuple[list[str], list[dict], list[str]]:
    """
    Chunking par paragraphes pour les documents non-CV.
    Respecte les sauts de paragraphe et attache les numéros de page.
    """
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    chunk_index = 0

    for page_num, page_text in pages:
        paragraphs = re.split(r"\n\s*\n", page_text)
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) < max_chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    _append_paragraph_chunk(
                        documents, metadatas, ids,
                        current_chunk, filename, doc_type, chunk_index, page_num,
                    )
                    chunk_index += 1
                current_chunk = para

        if current_chunk:
            _append_paragraph_chunk(
                documents, metadatas, ids,
                current_chunk, filename, doc_type, chunk_index, page_num,
            )
            chunk_index += 1

    # Correction des liens next/prev et total_chunks
    total = len(documents)
    for i, meta in enumerate(metadatas):
        meta["total_chunks"] = total
        meta["prev_chunk_id"] = f"{filename}_chunk_{i - 1}" if i > 0 else ""
        meta["next_chunk_id"] = f"{filename}_chunk_{i + 1}" if i < total - 1 else ""

    return documents, metadatas, ids


def _append_paragraph_chunk(
    documents, metadatas, ids,
    text: str, filename: str, doc_type: str, index: int, page_num: int,
):
    documents.append(text)
    metadatas.append({
        "source": filename,
        "doc_type": doc_type,
        "chunk_index": index,
        "total_chunks": 0,  # mis à jour après la boucle
        "section_name": f"Page {page_num}",
        "section_type": "CONTENU",
        "skills": "",
        "prev_chunk_id": "",
        "next_chunk_id": "",
        "page_number": page_num,
    })
    ids.append(f"{filename}_chunk_{index}")


def ingest_pdfs(pdf_dir: str = "./data/pdfs"):
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_or_create_collection(name="pdf_rag_collection")

    pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf"))
    if not pdf_files:
        print(f"Aucun PDF trouvé dans {pdf_dir}.")
        return

    for pdf_path in pdf_files:
        filename = Path(pdf_path).name
        print(f"\nTraitement du fichier : {filename}...")

        pages = extract_text_per_page(pdf_path)
        if not pages:
            print("-> Document vide ou illisible.")
            continue

        full_text = "\n".join(text for _, text in pages)
        doc_type = classify_document_type(full_text)
        print(f"-> Type détecté par l'IA : {doc_type}")

        if doc_type == "CV":
            documents, metadatas, ids = chunk_cv(pages, filename, doc_type)
            print(f"-> Chunking sémantique par sections (CV) : {len(documents)} chunks")
        else:
            documents, metadatas, ids = chunk_by_paragraphs(pages, filename, doc_type)
            print(f"-> Chunking par paragraphes ({doc_type}) : {len(documents)} chunks")

        if not documents:
            print("-> Aucun chunk généré.")
            continue

        collection.add(documents=documents, ids=ids, metadatas=metadatas)
        print(f"-> {len(documents)} chunks insérés avec succès.")

        # Résumé des sections pour les CVs
        if doc_type == "CV":
            for meta in metadatas:
                skills_preview = meta.get("skills", "")[:70]
                label = f"  [{meta['section_type']}] {meta['section_name'][:50]}"
                if skills_preview:
                    label += f" | Skills: {skills_preview}"
                print(label)


if __name__ == "__main__":
    os.makedirs("./data/pdfs", exist_ok=True)
    ingest_pdfs()
