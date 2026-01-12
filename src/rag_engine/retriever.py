import os
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Charger les variables d'environnement
load_dotenv()

def get_embeddings():
    """
    Charge le modèle d'embedding défini dans le .env
    """
    model_path = os.getenv('EMBEDDING_MODEL_PATH', '')
    
    if not model_path:
        raise ValueError("La variable EMBEDDING_MODEL_PATH n'est pas définie dans le .env")
    
    print(f"🔄 Chargement du modèle d'embedding : {model_path}...")
    
    embeddings = HuggingFaceEmbeddings(
        model_name=model_path,
        model_kwargs={'device': 'cpu'} 
    )
    return embeddings

def get_vectorstore():
    """
    Récupère la base de données vectorielle existante
    """
    persist_dir = os.getenv('CHROMA_DB_PATH', './chroma_db')
    embedding_function = get_embeddings()
    
    vectorstore = Chroma(
        persist_directory=persist_dir,
        embedding_function=embedding_function
    )
    return vectorstore

def query_rag(query_text, k=3):
    db = get_vectorstore()
    # Recherche par similarité
    results = db.similarity_search(query_text, k=k)
    return [doc.page_content for doc in results]