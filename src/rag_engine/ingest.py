import os
import glob
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from retriever import get_embeddings
from datasets import load_dataset
import pandas as pd
import json 

load_dotenv(dotenv_path='...\.env')

def data_path():
    current_file_path = Path(__file__).resolve()
    
    # 2. On remonte l'arborescence
    project_root = current_file_path.parent.parent.parent
    
    # 3. On construit le chemin cible proprement (OS agnostic)
    output_file = project_root / "data" 
    return output_file

DATA_PATH = data_path()
DB_PATH = os.getenv('CHROMA_DB_PATH', './chroma_db')

def ingest_documents():
    # 1. Chargement des documents
    print(f"Lecture des fichiers dans {DATA_PATH}...")
    documents = []
    json_file_path = DATA_PATH / "linux_commands.json"

    with json_file_path.open('r', encoding='utf-8') as f:
        data = json.load(f)

    # Au lieu de splitter un gros bloc, on itère sur chaque objet
    for entry in data:
        # On prépare le texte
        texte_riche = f"Action: {entry.get('fr')}\nCommande: {entry.get('completion')}"
        
        # On crée le document directement
        doc = Document(
            page_content=texte_riche,
            metadata={"category": entry.get('category')}
        )
        documents.append(doc)
    
    if not documents:
        print("Aucun document trouvé. Ajoutez des fichiers .txt dans le dossier /data")
        return

    print(f"{len(documents)} documents chargés.")

    # 2. Découpage en morceaux (Chunks)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


    chunks = text_splitter.split_documents(documents)
    print(f"Découpé en {len(chunks)} morceaux.")

    # 3. Création/Mise à jour de la base vectorielle
    print("Génération des embeddings et sauvegarde...")
    embedding_function = get_embeddings()
    
    Chroma.from_documents(
        documents=chunks, 
        embedding=embedding_function,
        persist_directory=DB_PATH
    )
    
    print(f"Ingestion terminée ! Base sauvegardée dans {DB_PATH}")

def load_hf_dataset():
    print("Téléchargement du dataset...")
    
    ds = load_dataset("missvector/linux-commands", split="train")
    df = ds.to_pandas()
    
    # 1. On récupère le chemin absolu du fichier actuel (ingest.py)
    current_file_path = Path(__file__).resolve()
    
    # 2. On remonte l'arborescence
    project_root = current_file_path.parent.parent.parent
    
    # 3. On construit le chemin cible proprement (OS agnostic)
    output_file = project_root / "data" / "linux_commands.json"

    # Création du dossier data s'il n'existe pas (via parents=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Sauvegarde vers : {output_file}")

    df.to_json(output_file, orient='records', indent=4, force_ascii=False)
    
    print("Terminé !")
    

if __name__ == "__main__":
    # load_hf_dataset()
    ingest_documents()