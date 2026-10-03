"""
Chunker sémantique pour les CVs.
Découpe le document en sections (Compétences, Expériences, Formation…)
et lie chaque chunk au précédent et au suivant.
"""
import re

# Patterns de détection des sections CV (français et anglais)
_SECTION_PATTERNS = [
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


_RE_PREFIX = re.compile(
    r"^(?:\d+[\.\)]\s*|art(?:icle)?\.?\s*\d*\.?\s*[-–]?\s*|§\s*\d*\.?\s*|[-–•]\s*)+",
    re.IGNORECASE,
)


def _detect_section(line: str) -> str | None:
    raw = line.strip()
    if not raw:
        return None
    # Nettoyer le préfixe numérique/bullet et la ponctuation terminale
    cleaned = _RE_PREFIX.sub("", raw).strip()
    cleaned = re.sub(r"[\s:;.\-–]+$", "", cleaned).strip()
    if not cleaned or len(cleaned) > 80:
        return None
    for pattern, section_type in _SECTION_PATTERNS:
        if re.match(pattern, cleaned):
            return section_type
    return None


def _split_into_sections(full_text: str) -> list[tuple[str, str, str]]:
    """Retourne [(section_name, section_type, section_text), ...]."""
    lines = full_text.split("\n")
    sections = []
    current_name = "ENTETE"
    current_type = "ENTETE"
    current_lines: list[str] = []

    for line in lines:
        section_type = _detect_section(line)
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


def _extract_skills(text: str) -> list[str]:
    raw = re.split(r"[\n,•\-\*·|/]", text)
    skills = []
    for item in raw:
        item = item.strip()
        if 2 < len(item) < 60 and not item.endswith("."):
            skills.append(item)
    return skills[:40]


def chunk_cv(
    pages: list[tuple[int, str]], filename: str, doc_type: str
) -> tuple[list[str], list[dict], list[str]]:
    """
    Un chunk par section CV.
    Métadonnées : section_name, section_type, skills, prev/next chunk ids.
    """
    full_text = "\n".join(text for _, text in pages)
    sections = _split_into_sections(full_text)
    valid = [(n, t, txt) for n, t, txt in sections if txt.strip()]
    total = len(valid)

    documents, metadatas, ids = [], [], []

    for i, (section_name, section_type, section_text) in enumerate(valid):
        chunk_id = f"{filename}_section_{i}"
        skills = _extract_skills(section_text) if section_type == "COMPETENCES" else []

        documents.append(f"[SECTION: {section_name}]\n{section_text}")
        metadatas.append({
            "source": filename,
            "doc_type": doc_type,
            "chunk_index": i,
            "total_chunks": total,
            "section_name": section_name,
            "section_type": section_type,
            "skills": ", ".join(skills),
            "prev_chunk_id": f"{filename}_section_{i - 1}" if i > 0 else "",
            "next_chunk_id": f"{filename}_section_{i + 1}" if i < total - 1 else "",
        })
        ids.append(chunk_id)

    return documents, metadatas, ids
