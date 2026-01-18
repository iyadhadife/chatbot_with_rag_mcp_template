import os
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from pathlib import Path
from sentence_transformers import SentenceTransformer

load_dotenv()

def get_embeddings():
    """
    Charge le modèle d'embedding défini dans le .env
    """
    
    model_name = os.getenv('EMBEDDING_MODEL_NAME', '')
    model_path = os.getenv('OUTPUT_FOLDER_MODEL', '')
    
    if not model_path:
        raise ValueError("La variable EMBEDDING_MODEL_PATH n'est pas définie dans le .env")
    
    print(f"🔄 Chargement du modèle d'embedding : {model_path}...")
    
    embeddings = HuggingFaceEmbeddings(
        model_name=model_path+'/'+model_name,
        model_kwargs={'device': 'cpu'} 
    )
    return embeddings

def get_vectorstore():
    """
    Récupère la base de données vectorielle existante
    """
    current_file_path = Path(__file__).resolve()
    project_root = current_file_path.parent.parent.parent
    persist_dir = str(project_root) + '/chroma_db'
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

def download():
    # 1. On charge les variables d'environnement
    load_dotenv()

    # Le nom sur Hugging Face (Source)
    # Ex: "sentence-transformers/all-MiniLM-L6-v2"
    model_name_hf = os.getenv('EMBEDDING_MODEL_PATH_HF')
    
    # Le dossier local où tu veux le mettre (Destination)
    # Ex: "models/embedding_model"
    save_path = os.getenv('LOCAL_FOLDER_MODEL', '\embedding_model') # Valeur par défaut conseillée

    # Vérification de sécurité
    if not model_name_hf:
        raise ValueError("❌ Erreur : La variable EMBEDDING_MODEL_PATH_HF est vide ou introuvable.")

    print(f"⬇️ Téléchargement depuis Hugging Face : {model_name_hf}")
    
    # CORRECTION 1 : On charge avec le NOM HF, pas le chemin local
    model = SentenceTransformer(model_name_hf)
    
    print(f"💾 Sauvegarde en cours dans : {save_path}")
    
    # CORRECTION 2 : .save() prend juste le chemin en argument
    model.save(os.getenv('OUTPUT_FOLDER_MODEL'))
    
    print("✅ Terminé ! Modèle sauvegardé.")
