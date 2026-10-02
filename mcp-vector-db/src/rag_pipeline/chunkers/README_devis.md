# Ingestion des Devis — Pipeline sémantique

## Vue d'ensemble

Le pipeline d'ingestion Devis transforme un PDF de devis en chunks indexés dans ChromaDB. La particularité : les devis contiennent des **tableaux de prestations** (lignes avec désignation, quantité, prix) qu'il ne faut jamais couper au milieu. Le chunker identifie les blocs tabulaires et les découpe proprement entre lignes complètes.

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
│  → document_id (12 hex chars)   │
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  _delete_existing_document()    │  supprime les anciens chunks
│  ChromaDB : DELETE by doc_id    │  (re-ingestion sans doublon)
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  classify_document_type()       │  Règles de vocabulaire (SANS LLM)
│  → "DEVIS"                       │  "devis", "prestations", "TTC",
│                                 │  "bon pour accord"… ≥ 2 termes → DEVIS
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  chunk_devis()                                                  │
│                                                                 │
│  ┌── Étape 1 : Découpe en sections métier ──────────────────┐  │
│  │                                                           │  │
│  │  _split_into_sections()                                   │  │
│  │       │                                                   │  │
│  │       ▼  Pour chaque ligne :                             │  │
│  │  ┌──────────────────────────────────────────────────┐    │  │
│  │  │  _detect_section(line)                           │    │  │
│  │  │  1. Supprimer préfixe ("1.", "Art. 2 -", "§")   │    │  │
│  │  │  2. Supprimer ponctuation terminale (":", "-")   │    │  │
│  │  │  3. Tester les 11 patterns prédéfinis            │    │  │
│  │  └──────────────────────────────────────────────────┘    │  │
│  │                                                           │  │
│  │  Si aucun pattern ne correspond → Fallback automatique :  │  │
│  │  ┌──────────────────────────────────────────────────┐    │  │
│  │  │  _infer_sections()   heuristiques                │    │  │
│  │  │  Critères pour détecter un titre inféré :        │    │  │
│  │  │  • Ligne courte (≤ 70 chars)                     │    │  │
│  │  │  • Isolée (entourée de lignes vides)             │    │  │
│  │  │  • MAJUSCULES ou Title Case ou "1. Titre"        │    │  │
│  │  │  • Pas de "€", "%", ni grand nombre              │    │  │
│  │  │  → section_type = "INFERRED"                     │    │  │
│  │  └──────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────┘  │  │
│                                                              │  │
│  Sections prédéfinies :                                      │  │
│  ┌────────────────────────┬─────────────────────────────┐   │  │
│  │ section_type           │ Exemples de titres          │   │  │
│  ├────────────────────────┼─────────────────────────────┤   │  │
│  │ OBJET                  │ Objet, Description mission… │   │  │
│  │ PRESTATIONS            │ Prestations, Services…      │   │  │
│  │ CONDITIONS_PAIEMENT    │ Paiement, Modalités…        │   │  │
│  │ TOTAUX                 │ Total, Récapitulatif, Tarif  │   │  │
│  │ VALIDITE               │ Validité du devis…          │   │  │
│  │ DELAIS                 │ Délais d'exécution…         │   │  │
│  │ CONDITIONS_GENERALES   │ CGV, Conditions générales…  │   │  │
│  │ CONTACT_EMETTEUR       │ Prestataire, Société…       │   │  │
│  │ CONTACT_CLIENT         │ Client, Destinataire…       │   │  │
│  │ GARANTIES              │ Garanties, SAV…             │   │  │
│  │ SIGNATURE              │ Bon pour accord…            │   │  │
│  │ ENTETE                 │ Tout avant la 1ère section  │   │  │
│  │ INFERRED               │ Détecté par heuristiques    │   │  │
│  └────────────────────────┴─────────────────────────────┘   │  │
│                                                              │  │
│  ┌── Étape 2 : Découpe intra-section (table-aware) ───────┐  │  │
│  │                                                         │  │  │
│  │  _split_section_into_chunks()                           │  │  │
│  │       │                                                 │  │  │
│  │       ▼                                                 │  │  │
│  │  _parse_blocks() → blocs TABLE ou PROSE                 │  │  │
│  │       │                                                 │  │  │
│  │       ├─ Bloc TABLE ──────────────────────────────────┐ │  │  │
│  │       │  _is_table_line() : "|" ou ≥2 colonnes        │ │  │  │
│  │       │  _split_table_block()                         │ │  │  │
│  │       │  • Identifier les lignes d'en-tête            │ │  │  │
│  │       │  • Couper entre lignes complètes seulement    │ │  │  │
│  │       │  • Répéter l'en-tête dans chaque sous-chunk   │ │  │  │
│  │       │  MAX_CHUNK_CHARS = 1200                        │ │  │  │
│  │       └───────────────────────────────────────────────┘ │  │  │
│  │       │                                                 │  │  │
│  │       └─ Bloc PROSE ─────────────────────────────────┐  │  │  │
│  │          _split_prose_block()                         │  │  │  │
│  │          • Couper aux doubles sauts de ligne          │  │  │  │
│  │          • Fusionner paragraphes courts si possible   │  │  │  │
│  │          MAX_CHUNK_CHARS = 1200                        │  │  │  │
│  │          └───────────────────────────────────────────┘  │  │  │
│  └─────────────────────────────────────────────────────┘  │  │
│                                                              │  │
│  ┌── Étape 3 : Extraction de métadonnées spécifiques ─────┐  │  │
│  │  _extract_amounts()    → montants en € dans le chunk    │  │  │
│  │  _extract_tva()        → taux de TVA                    │  │  │
│  │  _extract_dates()      → dates (format jj/mm/aaaa…)     │  │  │
│  │  _extract_devis_number() → N° ou référence du devis     │  │  │
│  │  _extract_line_items() → lignes de prestation           │  │  │
│  └─────────────────────────────────────────────────────┘  │  │
└─────────────────────────────────────────────────────────────┘
     │
     │  [(doc_text, metadata, chunk_id), ...]
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  MetadataGenerator.generate_document_metadata()   SANS LLM      │
│  → DocumentMeta (Pydantic)                                      │
│  • keywords : YAKE   • summary : TextRank                       │
│  • organisation/auteur : heuristique   • montants/dates : regex │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  MetadataGenerator.generate_chunk_metadata()                    │
│  Par chunk — heuristiques YAKE+regex SANS LLM (défaut)          │
│  ou LLM optionnel (ENRICH_CHUNKS=true, lent sur CPU)           │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Fusion des métadonnées                                         │
│  doc_meta_flat ← chunk_meta_flat ← chunker_meta ← document_id  │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  flatten_for_chroma()           │  listes → JSON string
└─────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  collection.add(...)            │
│  ChromaDB                       │
└─────────────────────────────────┘
```

---

## Découpe table-aware — Détail

L'enjeu principal d'un devis est de **ne pas couper une ligne de prestation** (ex : `Développement API  3j  2100 €`) au milieu d'un chunk. Le mécanisme :

```
Section PRESTATIONS (texte brut)
        │
        ▼
_parse_blocks()
        │
        ├── Bloc TABLE  (lignes colonisées ou contenant "|")
        │       │
        │       ▼
        │   En-tête répété en tête de chaque sous-chunk
        │   ┌─────────────────────────────────┐
        │   │ DÉSIGNATION   QTÉ   PU    TOTAL │  ← répété
        │   │ ─────────────────────────────── │  ← répété
        │   │ Audit sécurité  1   800€   800€ │
        │   │ Rapport final   1   200€   200€ │
        │   └─────────────────────────────────┘
        │
        └── Bloc PROSE  (texte libre entre tableaux)
                │
                ▼
            Coupure aux paragraphes (double \n)
```

---

## Structure d'un chunk Devis

```
[SECTION: Détail des prestations (1/2)]
DÉSIGNATION              QTÉ   PU HT     TOTAL HT
────────────────────────────────────────────────
Développement agent IA    5j   850 €   4 250 €
Intégration API externe   2j   850 €   1 700 €
```

**Métadonnées indexées :**

| Champ | Source | Exemple |
|---|---|---|
| `source` | chunker | `devis_agent_prospection.pdf` |
| `doc_type` | ingest | `DEVIS` |
| `document_id` | MD5 | `b7e2a1f04c89` |
| `section_type` | pattern | `PRESTATIONS` |
| `section_name` | texte brut | `Détail des prestations` |
| `devis_number` | regex | `DEV-2024-042` |
| `amounts` | regex | `4250 €, 1700 €` |
| `tva_rate` | regex | `20` |
| `dates` | regex | `15/03/2024` |
| `line_items_count` | regex | `2` |
| `doc_title` | 1ʳᵉ ligne / filename | `Devis Agent de Prospection IA` |
| `summary` | TextRank | `Devis pour développement…` |
| `keywords` | YAKE | `["agent prospection","ia","devis"]` |
| `prev_chunk_id` | chunker | `devis_…_section_1` |
| `next_chunk_id` | chunker | `devis_…_section_3` |

---

## Fichiers concernés

| Fichier | Rôle |
|---|---|
| `chunkers/devis_chunker.py` | Sections + blocs table/prose + extraction métadonnées |
| `text_analysis.py` | Classification (règles) + YAKE + TextRank + regex — **sans LLM** |
| `ingest.py` | Orchestration : PDF → ChromaDB |
| `metadata_generator.py` | Assemblage des métadonnées document/chunk |
| `retriever.py` | Recherche sémantique + reranking |

---

## Outils MCP exposés pour les Devis

| Outil MCP | Filtre ChromaDB | Usage |
|---|---|---|
| `search_devis` | `doc_type=DEVIS` | Recherche globale dans tous les devis |
| `search_devis_prestations` | `doc_type=DEVIS, section_type=PRESTATIONS` | Lignes de service, prix |
| `search_devis_totaux` | `doc_type=DEVIS, section_type=TOTAUX` | Montants HT/TVA/TTC |
| `search_devis_conditions` | `doc_type=DEVIS, section_type=CONDITIONS_PAIEMENT` | Modalités de règlement |

---

## Variables d'environnement

| Variable | Défaut | Effet |
|---|---|---|
| `ENRICH_CHUNKS` | `false` | `true` = LLM par chunk (lent sur CPU, optionnel) |
| `OLLAMA_MODEL` | `qwen2.5:0.5b` | Utilisé **uniquement** si `ENRICH_CHUNKS=true` |
| `MAX_RETRIEVAL_DISTANCE` | `1.2` | Seuil cosine pour le reranking |

> **Note CPU :** par défaut l'ingestion n'appelle **aucun LLM** (ni classification, ni métadonnées document). Tout est calculé par règles + YAKE + TextRank + regex.
