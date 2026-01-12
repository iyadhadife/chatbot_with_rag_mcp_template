import os
import glob
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
# On importe la fonction qu'on vient de créer pour garantir la cohérence
from src.rag_engine.retriever import get_embeddings
from datasets import load_dataset

load_dotenv(dotenv_path='...\.env')

DATA_PATH = "./data"
DB_PATH = os.getenv('CHROMA_DB_PATH', './chroma_db')

def ingest_documents():
    # 1. Chargement des documents
    print(f"Lecture des fichiers dans {DATA_PATH}...")
    
    # Exemple pour fichiers .txt 
    loader = DirectoryLoader(DATA_PATH, glob="**/*.txt", loader_cls=TextLoader)
    documents = loader.load()
    
    if not documents:
        print("Aucun document trouvé. Ajoutez des fichiers .txt dans le dossier /data")
        return

    print(f"{len(documents)} documents chargés.")

    # 2. Découpage en morceaux (Chunks)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
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

def load_dataset():
    ds = load_dataset("missvector/linux-commands", "fr")
    ds['train'].to_csv()

if __name__ == "__main__":
    ingest_documents()