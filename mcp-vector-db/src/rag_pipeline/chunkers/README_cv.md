# Ingestion des CVs — Pipeline sémantique

## Vue d'ensemble

Le pipeline d'ingestion CV transforme un fichier PDF brut en chunks indexés dans ChromaDB, enrichis de métadonnées structurées. Chaque chunk correspond à **une section du CV** (Compétences, Expériences, Formation…).

---

## Schéma fonctionnel

```
PDF (fichier)
     │
     ▼
┌─────────────────────────────────┐
│  extract_text_per_page()        │  pypdf — extraction page par page
│  → [(page_num, texte), ...]     │
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  compute_document_id()          │  MD5(filename :: full_text)[:12]
│  → document_id (12 hex chars)   │  identifiant stable pour déduplication
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  _delete_existing_document()    │  supprime les anciens chunks si le
│  ChromaDB : DELETE by doc_id    │  document a déjà été indexé
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  classify_document_type()       │  Règles de vocabulaire (SANS LLM)
│  → "CV"                         │  scoring : "compétences", "formation",
│                                 │  "expériences"… ≥ 2 termes → CV
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  chunk_cv()                                                     │
│                                                                 │
│  full_text                                                      │
│      │                                                          │
│      ▼                                                          │
│  _split_into_sections()                                         │
│      │                                                          │
│      │  Pour chaque ligne du texte :                            │
│      │  ┌─────────────────────────────────────────────────┐    │
│      │  │  _detect_section(line)                          │    │
│      │  │  1. Nettoyer le préfixe ("1.", "Art.", "§"…)   │    │
│      │  │  2. Nettoyer la ponctuation terminale (":", "-")│    │
│      │  │  3. Tester les patterns CV prédéfinis           │    │
│      │  └─────────────────────────────────────────────────┘    │
│      │                                                          │
│      ▼                                                          │
│  [(section_name, section_type, section_text), ...]             │
│                                                                 │
│  Sections détectées :                                           │
│  ┌──────────────────┬────────────────────────────────────┐     │
│  │ section_type     │ Exemples de titres reconnus         │     │
│  ├──────────────────┼────────────────────────────────────┤     │
│  │ COMPETENCES      │ Compétences, Skills, Stack Tech…   │     │
│  │ EXPERIENCES      │ Expériences Pro, Work Experience…  │     │
│  │ FORMATION        │ Formation, Éducation, Diplômes…    │     │
│  │ LANGUES          │ Langues, Languages                  │     │
│  │ PROJETS          │ Projets, Portfolio, Réalisations…  │     │
│  │ CERTIFICATIONS   │ Certifications, Accréditations…    │     │
│  │ PROFIL           │ Profil, Résumé, Summary, Objectif… │     │
│  │ LOISIRS          │ Loisirs, Hobbies, Centres d'intérêt│     │
│  │ CONTACT          │ Contact, Coordonnées, Informations  │     │
│  │ ENTETE           │ Tout ce qui précède la 1ère section │     │
│  └──────────────────┴────────────────────────────────────┘     │
│                                                                 │
│  _extract_skills() — si section_type == COMPETENCES            │
│  → liste de compétences extraites (split sur , • - / |)        │
└─────────────────────────────────────────────────────────────────┘
     │
     │  [(doc_text, metadata, chunk_id), ...]
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  MetadataGenerator.generate_document_metadata()   SANS LLM      │
│  → DocumentMeta (Pydantic)                                      │
│                                                                 │
│  • keywords  : YAKE          (mots-clés multi-mots statistiques)│
│  • summary   : TextRank      (résumé extractif, networkx)       │
│  • entities  : regex emails + heuristique auteur/organisation   │
│  • creation_date / montants / dates : extract_universal_fields  │
│  • title     : 1ʳᵉ ligne courte, sinon nom de fichier           │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  MetadataGenerator.generate_chunk_metadata()                    │
│  Par chunk — heuristiques SANS LLM (ENRICH_CHUNKS=false, défaut)│
│  ou LLM optionnel            (ENRICH_CHUNKS=true, lent sur CPU) │
│                                                                 │
│  Heuristiques : mots-clés YAKE + entités regex (majuscules)     │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Fusion des métadonnées (par ordre de priorité croissante)      │
│                                                                 │
│  doc_meta_flat                                                  │
│      ← chunk_meta_flat  (écrase si conflit)                     │
│          ← chunker_meta  (source, section_type…)               │
│              ← document_id  (toujours ajouté)                   │
│              ← doc_title                                        │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  flatten_for_chroma()           │  listes → JSON string
│  ChromaDB n'accepte pas les     │  (contrainte ChromaDB)
│  listes en métadonnées          │
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  collection.add(                │
│    documents=[...],             │
│    metadatas=[...],             │
│    ids=[...],                   │
│  )                              │
│  ChromaDB — 1 chunk = 1 section │
└─────────────────────────────────┘
```

---

## Structure d'un chunk CV

```
[SECTION: Compétences techniques]
Python, FastAPI, LangChain, Docker, PostgreSQL...
```

**Métadonnées indexées :**

| Champ | Source | Exemple |
|---|---|---|
| `source` | chunker | `CV_Ingenieur_IA.pdf` |
| `doc_type` | ingest | `CV` |
| `document_id` | MD5 | `a3f1c9e20b4d` |
| `section_type` | pattern | `COMPETENCES` |
| `section_name` | texte brut | `Compétences techniques` |
| `skills` | `_extract_skills()` | `Python, Docker, FastAPI` |
| `doc_title` | 1ʳᵉ ligne / filename | `CV Ingénieur IA — Jean Dupont` |
| `summary` | TextRank | `Ingénieur IA avec 5 ans d'expérience…` |
| `keywords` | YAKE | `["machine learning","python","rag"]` (JSON string) |
| `local_summary` | heuristique | première phrase non vide du chunk |
| `chunk_index` | chunker | `2` |
| `prev_chunk_id` | chunker | `CV_…_section_1` |
| `next_chunk_id` | chunker | `CV_…_section_3` |

---

## Fichiers concernés

| Fichier | Rôle |
|---|---|
| `chunkers/cv_chunker.py` | Détection de sections + extraction de compétences |
| `text_analysis.py` | Classification (règles) + YAKE + TextRank + regex — **sans LLM** |
| `ingest.py` | Orchestration : PDF → ChromaDB |
| `metadata_generator.py` | Assemblage des métadonnées document/chunk |
| `retriever.py` | Recherche sémantique + reranking |

---

## Variables d'environnement

| Variable | Défaut | Effet |
|---|---|---|
| `ENRICH_CHUNKS` | `false` | `true` = LLM par chunk (lent sur CPU, optionnel) |
| `OLLAMA_MODEL` | `qwen2.5:0.5b` | Utilisé **uniquement** si `ENRICH_CHUNKS=true` |
| `MAX_RETRIEVAL_DISTANCE` | `1.2` | Seuil cosine pour le reranking |

> **Note CPU :** par défaut l'ingestion n'appelle **aucun LLM** (ni classification, ni métadonnées document). Tout est calculé par règles + YAKE + TextRank + regex.
