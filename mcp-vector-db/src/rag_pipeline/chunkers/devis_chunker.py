"""
Chunker sémantique pour les devis.
Découpe le document en sections métier puis, à l'intérieur de chaque section,
identifie les blocs tabulaires pour ne jamais couper une ligne de table en son milieu.

Stratégie de découpe intra-section :
  1. Parser le texte en blocs : TABLE (lignes colonisées) ou PROSE (texte libre)
  2. Bloc TABLE  → couper uniquement entre des lignes complètes ; garder le header
                   avec sa première "tranche" de données.
  3. Bloc PROSE  → couper aux paragraphes (double saut de ligne).
  4. Si un bloc tient dans MAX_CHUNK_CHARS, ne pas le découper du tout.
"""
import re
from dataclasses import dataclass, field

# ── Paramètres ────────────────────────────────────────────────────────────────

MAX_CHUNK_CHARS = 1200   # taille max d'un chunk (caractères, pas tokens)
MIN_COLS_FOR_TABLE = 2   # nb de colonnes minimum pour considérer une ligne comme tabulaire
MIN_COL_SPACING = 2      # espaces consécutifs minimum entre colonnes

# ── Patterns de sections ──────────────────────────────────────────────────────
# Chaque pattern est testé sur la ligne NETTOYÉE (sans préfixe numérique ni ponctuation).
# Ex : "1. Objet du devis :" → nettoyé → "Objet du devis"

_SECTION_PATTERNS = [
    (r"(?i)^(OBJET(\s+DU\s+DEVIS)?|DESCRIPTION\s+DES?\s+TRAVAUX|DESCRIPTION\s+DE\s+LA\s+MISSION|NATURE\s+DES?\s+TRAVAUX|CONTEXTE|INTITULÉ)", "OBJET"),
    (r"(?i)^(DÉTAIL\s+DES?\s+PRESTATIONS?|PRESTATIONS?|DÉSIGNATION|LIGNES?\s+DE\s+DEVIS|DÉTAIL\s+DES?\s+TRAVAUX|POSTES?|ARTICLES?|SERVICES?|FOURNITURES?|MISSIONS?)", "PRESTATIONS"),
    (r"(?i)^(CONDITIONS?\s+DE\s+PAIEMENT|MODALITÉS?\s+DE\s+(RÈGLEMENT|PAIEMENT)|PAIEMENT|RÈGLEMENT|FACTURATION|ÉCHÉANCIER)", "CONDITIONS_PAIEMENT"),
    (r"(?i)^(TOTAL|RÉCAPITULATIF(\s+FINANCIER)?|MONTANTS?|RÉSUMÉ\s+FINANCIER|SYNTHÈSE(\s+FINANCIÈRE)?|PRIX\s+TOTAL|TARIF)", "TOTAUX"),
    (r"(?i)^(VALIDITÉ(\s+DU\s+DEVIS)?|DURÉE\s+DE\s+VALIDITÉ|DÉLAIS?\s+DE\s+RÉPONSE|OFFRE\s+VALABLE|DURÉE\s+DE\s+L.OFFRE)", "VALIDITE"),
    (r"(?i)^(DÉLAIS?\s+D.EXÉCUTION|DÉLAIS?\s+DE\s+(LIVRAISON|RÉALISATION)|PLANNING|CALENDRIER(\s+PRÉVISIONNEL)?|ÉCHÉANCIER\s+DE\s+RÉALISATION)", "DELAIS"),
    (r"(?i)^(CONDITIONS?\s+GÉNÉRALES?(\s+DE\s+VENTE)?|CGV|CONDITIONS?\s+PARTICULIÈRES?|CLAUSES?|MENTIONS?\s+LÉGALES?)", "CONDITIONS_GENERALES"),
    (r"(?i)^(COORDONNÉES?(\s+DE\s+L.ÉMETTEUR)?|CONTACT|ÉMETTEUR|PRESTATAIRE|VENDEUR|SOCIÉTÉ|ENTREPRISE|NOS\s+COORDONNÉES?|NOUS\s+CONTACTER)", "CONTACT_EMETTEUR"),
    (r"(?i)^(CLIENT|DESTINATAIRE|ACHETEUR|BÉNÉFICIAIRE|COORDONNÉES?\s+CLIENT|À\s+L.ATTENTION)", "CONTACT_CLIENT"),
    (r"(?i)^(GARANTIES?|SAV|SERVICE\s+APRÈS.VENTE|SUPPORT)", "GARANTIES"),
    (r"(?i)^(SIGNATURE|BON\s+POUR\s+ACCORD|ACCEPTATION|APPROBATION)", "SIGNATURE"),
]

# Préfixes à ignorer avant de tester les patterns (numéros, tirets, Art., §…)
_RE_SECTION_PREFIX = re.compile(
    r"^(?:\d+[\.\)]\s*|art(?:icle)?\.?\s*\d*\.?\s*[-–]?\s*|§\s*\d*\.?\s*|[-–•]\s*)+",
    re.IGNORECASE,
)

# ── Regex métadonnées ─────────────────────────────────────────────────────────

_RE_MONTANT   = re.compile(r"(\d[\d\s]*[,.]?\d*)\s*€", re.IGNORECASE)
_RE_TVA       = re.compile(r"TVA\s*[:\s]\s*(\d+(?:[,.]\d+)?)\s*%", re.IGNORECASE)
_RE_DATE      = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})\b")
_RE_DEVIS_NUM = re.compile(r"(?:N°|NUM[ÉE]RO|REF|RÉFÉRENCE)[^\w]*([A-Z0-9\-_/]{3,20})", re.IGNORECASE)

# Ligne de séparation de tableau (tirets, +, =)
_RE_SEPARATOR = re.compile(r"^[\s\-=+|]{3,}$")

# ── Détection de structure tabulaire ─────────────────────────────────────────

def _is_table_line(line: str) -> bool:
    """
    Une ligne est considérée tabulaire si :
      - elle contient un '|' (table Markdown / PDF extrait avec |)
      - OU elle a au moins MIN_COLS_FOR_TABLE colonnes séparées par MIN_COL_SPACING espaces
      - OU c'est une ligne de séparation (tirets…)
    """
    if "|" in line and line.count("|") >= MIN_COLS_FOR_TABLE - 1:
        return True
    if _RE_SEPARATOR.match(line):
        return True
    # Colonnes par espaces multiples
    cols = re.split(r" {%d,}" % MIN_COL_SPACING, line.strip())
    return len(cols) >= MIN_COLS_FOR_TABLE


def _is_header_line(line: str) -> bool:
    """Heuristique : ligne d'en-tête de tableau (majuscules ou soulignée)."""
    stripped = line.strip()
    if not stripped:
        return False
    # Ligne entièrement en majuscules avec séparateurs
    words = re.findall(r"\b\w+\b", stripped)
    if words and sum(1 for w in words if w.isupper()) / len(words) > 0.6:
        return True
    return False


# ── Blocs intra-section ───────────────────────────────────────────────────────

@dataclass
class _Block:
    kind: str          # "table" | "prose"
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def char_count(self) -> int:
        return len(self.text)


def _parse_blocks(text: str) -> list[_Block]:
    """
    Segmente le texte d'une section en blocs TABLE / PROSE consécutifs.
    Les lignes vides séparent les blocs prose mais sont intégrées au bloc table
    si elles sont encadrées par des lignes tabulaires (tableaux multi-lignes).
    """
    lines = text.split("\n")
    blocks: list[_Block] = []
    current: _Block | None = None

    for line in lines:
        kind = "table" if _is_table_line(line) else "prose"

        # Ligne vide : on la rattache au bloc en cours si c'est une table,
        # sinon elle marque une transition prose → prose (nouveau paragraphe)
        if not line.strip():
            if current and current.kind == "table":
                current.lines.append(line)
            else:
                if current:
                    blocks.append(current)
                current = None
            continue

        if current is None:
            current = _Block(kind=kind)
        elif current.kind != kind:
            blocks.append(current)
            current = _Block(kind=kind)

        current.lines.append(line)

    if current:
        blocks.append(current)

    return [b for b in blocks if b.lines]


# ── Découpe intelligente d'un bloc ───────────────────────────────────────────

def _split_table_block(block: _Block, header_lines: list[str]) -> list[str]:
    """
    Découpe un bloc TABLE en sous-chunks sans couper une ligne de prestation.
    Le header est répété au début de chaque sous-chunk pour conserver le contexte.
    """
    header_text = "\n".join(header_lines)
    header_len  = len(header_text) + 1  # +1 pour \n

    chunks = []
    current_lines: list[str] = list(header_lines)
    current_len = header_len

    for line in block.lines:
        if _is_header_line(line) and not current_lines[len(header_lines):]:
            # On est encore dans le header, on l'accumule
            current_lines.append(line)
            current_len += len(line) + 1
            continue

        line_len = len(line) + 1

        if current_len + line_len > MAX_CHUNK_CHARS and len(current_lines) > len(header_lines):
            # Sauvegarder le chunk courant et repartir avec le header
            chunks.append("\n".join(current_lines))
            current_lines = list(header_lines) + [line]
            current_len = header_len + line_len
        else:
            current_lines.append(line)
            current_len += line_len

    if len(current_lines) > len(header_lines):
        chunks.append("\n".join(current_lines))

    return chunks or [block.text]


def _split_prose_block(block: _Block) -> list[str]:
    """
    Découpe un bloc PROSE aux paragraphes (double saut de ligne).
    Ne fusionne des paragraphes que s'ils tiennent dans MAX_CHUNK_CHARS.
    """
    # Regrouper les lignes en paragraphes
    paragraphs: list[str] = []
    current: list[str] = []
    for line in block.lines:
        if not line.strip() and current:
            paragraphs.append("\n".join(current))
            current = []
        elif line.strip():
            current.append(line)
    if current:
        paragraphs.append("\n".join(current))

    chunks: list[str] = []
    acc = ""
    for para in paragraphs:
        candidate = (acc + "\n\n" + para).strip() if acc else para
        if len(candidate) <= MAX_CHUNK_CHARS:
            acc = candidate
        else:
            if acc:
                chunks.append(acc)
            # Paragraphe individuel trop long → on le garde tel quel (ne pas couper)
            acc = para
    if acc:
        chunks.append(acc)

    return chunks or [block.text]


def _split_section_into_chunks(section_text: str) -> list[str]:
    """
    Point d'entrée : découpe intelligente d'une section en chunks.
    Identifie les blocs tabulaires/prose et applique la stratégie adaptée.
    """
    # Si la section tient entière, pas la peine de découper
    if len(section_text) <= MAX_CHUNK_CHARS:
        return [section_text]

    blocks = _parse_blocks(section_text)
    result: list[str] = []

    for block in blocks:
        if block.kind == "table":
            # Identifier les lignes d'en-tête au début du bloc
            header_lines: list[str] = []
            for line in block.lines:
                if _is_header_line(line) or _RE_SEPARATOR.match(line):
                    header_lines.append(line)
                else:
                    break

            if block.char_count <= MAX_CHUNK_CHARS:
                result.append(block.text)
            else:
                result.extend(_split_table_block(block, header_lines))
        else:
            if block.char_count <= MAX_CHUNK_CHARS:
                result.append(block.text)
            else:
                result.extend(_split_prose_block(block))

    return result or [section_text]


# ── Détection de section ──────────────────────────────────────────────────────

def _detect_section(line: str) -> str | None:
    """
    Détecte si une ligne est un titre de section.
    Supporte les préfixes numériques ("1.", "Art. 2 -", "§3") et les
    deux-points terminaux ("Objet :").  La ligne nettoyée est testée
    contre chaque pattern.
    """
    raw = line.strip()
    if not raw:
        return None

    # Supprimer le préfixe numérique / bullet éventuel
    cleaned = _RE_SECTION_PREFIX.sub("", raw).strip()
    # Supprimer la ponctuation terminale (" :", " -", "…")
    cleaned = re.sub(r"[\s:;.\-–]+$", "", cleaned).strip()

    # La ligne nettoyée doit être courte pour être un titre (pas un paragraphe)
    if not cleaned or len(cleaned) > 80:
        return None

    for pattern, section_type in _SECTION_PATTERNS:
        if re.match(pattern, cleaned):
            return section_type

    return None


def _is_inferred_header(lines: list[str], idx: int) -> bool:
    """
    Heuristiques pour détecter un titre de section non prévu dans les patterns :
      - Ligne courte (≤ 70 chars) et non vide
      - Non tabulaire
      - Précédée ou suivie d'une ligne vide (ou en début de document)
      - Soit en MAJUSCULES, soit en Title Case, soit préfixée par un numéro
      - Ne ressemble pas à une valeur de champ (pas de chiffres dominants, pas de "€")
    """
    line = lines[idx].strip()
    if not line or len(line) > 70 or _is_table_line(line):
        return False

    # Pas de valeurs monétaires ou pourcentages (c'est une ligne de données)
    if re.search(r"[\d]+\s*€|%|\d{4,}", line):
        return False

    # Doit être précédée ou suivie d'une ligne vide (isolée)
    prev_empty = idx == 0 or not lines[idx - 1].strip()
    next_empty = idx == len(lines) - 1 or not lines[idx + 1].strip()
    if not (prev_empty or next_empty):
        return False

    cleaned = _RE_SECTION_PREFIX.sub("", line).strip()
    cleaned = re.sub(r"[\s:;.\-–]+$", "", cleaned).strip()
    if not cleaned:
        return False

    words = re.findall(r"\b[A-ZÀ-Ÿa-zà-ÿ]{2,}\b", cleaned)
    if not words:
        return False

    # En majuscules ?
    if sum(1 for w in words if w.isupper()) / len(words) >= 0.5:
        return True
    # En Title Case (première lettre maj pour chaque mot significatif) ?
    if sum(1 for w in words if w[0].isupper()) / len(words) >= 0.6 and len(words) <= 6:
        return True
    # Préfixe numérique conservé dans le brut (ex : "1. Contexte")
    if re.match(r"^\d+[\.\)]\s+\w", line):
        return True

    return False


def _infer_sections(full_text: str) -> list[tuple[str, str, str]]:
    """
    Fallback : découpe le document par heuristiques quand aucun pattern
    prédéfini ne correspond.  Chaque titre inféré devient une section
    avec section_type="INFERRED".
    """
    lines = full_text.split("\n")
    sections: list[tuple[str, str, str]] = []
    current_name = "ENTETE"
    current_type = "ENTETE"
    current_lines: list[str] = []

    for i, line in enumerate(lines):
        if _is_inferred_header(lines, i):
            if current_lines:
                sections.append((current_name, current_type, "\n".join(current_lines)))
            current_name = line.strip()
            current_type = "INFERRED"
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_name, current_type, "\n".join(current_lines)))

    return sections


def _split_into_sections(full_text: str) -> list[tuple[str, str, str]]:
    """
    Découpe en sections métier.
    1. Essaie les patterns prédéfinis.
    2. Si aucune section n'est trouvée (tout reste en ENTETE),
       bascule sur la détection heuristique automatique.
    """
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

    # Fallback : si toutes les sections sont ENTETE → aucun pattern n'a matché
    unique_types = {t for _, t, txt in sections if txt.strip()}
    if unique_types <= {"ENTETE"}:
        inferred = _infer_sections(full_text)
        inferred_types = {t for _, t, _ in inferred}
        # N'utiliser le fallback que s'il a trouvé plus qu'ENTETE seul
        if inferred_types - {"ENTETE"}:
            print("  ℹ Sections inférées automatiquement (aucun pattern prédéfini ne correspondait)")
            return inferred

    return sections


# ── Extracteurs de métadonnées ────────────────────────────────────────────────

def _extract_amounts(text: str) -> list[str]:
    return [m.group(0).strip() for m in _RE_MONTANT.finditer(text)][:10]

def _extract_tva(text: str) -> str:
    m = _RE_TVA.search(text)
    return m.group(1) if m else ""

def _extract_dates(text: str) -> list[str]:
    return list(dict.fromkeys(_RE_DATE.findall(text)))[:5]

def _extract_devis_number(text: str) -> str:
    m = _RE_DEVIS_NUM.search(text)
    return m.group(1) if m else ""

def _extract_line_items(text: str) -> list[str]:
    items = []
    pattern = re.compile(
        r"^(.{5,60}?)\s{2,}(\d+[\s,.]?\d*)\s{1,}(\d[\d\s,.]*€?)\s*$",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        items.append(m.group(0).strip())
    return items[:30]


# ── Chunker principal ─────────────────────────────────────────────────────────

def debug_sections(pages: list[tuple[int, str]]) -> None:
    """
    Affiche les lignes détectées comme titres de section.
    Appeler manuellement pour diagnostiquer un devis non détecté.
    """
    full_text = "\n".join(text for _, text in pages)
    print("=== DEBUG sections devis ===")
    for i, line in enumerate(full_text.split("\n")):
        section = _detect_section(line)
        if section:
            print(f"  L{i:03d} [{section:25s}] ← {repr(line[:80])}")
        elif line.strip() and len(line.strip()) < 60:
            # Lignes courtes non reconnues : candidats potentiels manqués
            print(f"  L{i:03d} [{'?':25s}]   {repr(line[:80])}")
    print("=== FIN DEBUG ===")


def chunk_devis(
    pages: list[tuple[int, str]], filename: str, doc_type: str
) -> tuple[list[str], list[dict], list[str]]:
    """
    Chunking sémantique pour les devis.

    Pipeline :
      1. Découpe en sections métier (ENTETE, PRESTATIONS, TOTAUX…)
      2. Pour chaque section : découpe en sous-chunks en respectant les
         frontières de lignes tabulaires (jamais de coupure en milieu de ligne)
      3. Enrichit chaque chunk avec les métadonnées extraites
    """
    full_text = "\n".join(text for _, text in pages)
    sections = _split_into_sections(full_text)
    valid_sections = [(n, t, txt) for n, t, txt in sections if txt.strip()]

    devis_number = _extract_devis_number(full_text[:2000])

    # Construire la liste plate de tous les chunks (une section peut → N chunks)
    flat_chunks: list[tuple[str, str, str]] = []  # (section_name, section_type, chunk_text)

    for section_name, section_type, section_text in valid_sections:
        sub_chunks = _split_section_into_chunks(section_text)
        total_sub = len(sub_chunks)
        for sub_i, chunk_text in enumerate(sub_chunks):
            # Ajouter un suffixe si la section est découpée en plusieurs parties
            label = section_name if total_sub == 1 else f"{section_name} ({sub_i + 1}/{total_sub})"
            flat_chunks.append((label, section_type, chunk_text))

    total = len(flat_chunks)
    documents, metadatas, ids = [], [], []

    for i, (section_name, section_type, chunk_text) in enumerate(flat_chunks):
        chunk_id = f"{filename}_devis_section_{i}"

        # Pour les sections inférées, on extrait tout (type inconnu)
        inferred = section_type == "INFERRED"
        amounts    = _extract_amounts(chunk_text)    if inferred or section_type in ("PRESTATIONS", "TOTAUX", "ENTETE") else []
        tva        = _extract_tva(chunk_text)        if inferred or section_type in ("PRESTATIONS", "TOTAUX") else ""
        dates      = _extract_dates(chunk_text)      if inferred or section_type in ("ENTETE", "VALIDITE", "DELAIS") else []
        line_items = _extract_line_items(chunk_text) if inferred or section_type == "PRESTATIONS" else []

        documents.append(f"[SECTION: {section_name}]\n{chunk_text}")
        metadatas.append({
            "source":             filename,
            "doc_type":           doc_type,
            "chunk_index":        i,
            "total_chunks":       total,
            "section_name":       section_name,
            "section_type":       section_type,
            "devis_number":       devis_number,
            "amounts":            ", ".join(amounts),
            "tva_rate":           tva,
            "dates":              ", ".join(dates),
            "line_items_count":   len(line_items),
            "line_items_preview": " | ".join(line_items[:5]),
            "skills":             "",   # champ uniforme avec les autres types
            "prev_chunk_id":      f"{filename}_devis_section_{i - 1}" if i > 0     else "",
            "next_chunk_id":      f"{filename}_devis_section_{i + 1}" if i < total - 1 else "",
        })
        ids.append(chunk_id)

    return documents, metadatas, ids
