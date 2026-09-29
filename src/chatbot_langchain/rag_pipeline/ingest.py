import os
import glob
from pathlib import Path
import chromadb
from pypdf import PdfReader
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

# Connexion ChromaDB (via HTTP vers le conteneur ou en local selon votre config)
CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        print(f"Erreur lecture {pdf_path}: {e}")
        return ""

def classify_document_type(text_sample: str) -> str:
    """Utilise le LLM local pour classifier automatiquement le type de document."""
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    
    llm = ChatOllama(
        model="qwen2.5:7b",
        base_url=ollama_base_url,
        temperature=0.0
    )
    
    prompt = [
        SystemMessage(content="Tu es un classificateur de documents professionnels. Réponds UNIQUEMENT par un mot clé court en majuscules (ex: CV, DEVIS, FACTURE, CONTRAT, RAPPORT, AUTRE) qui qualifie le document fourni."),
        HumanMessage(content=f"Voici le début du document :\n\n{text_sample[:1500]}")
    ]
    
    try:
        response = llm.invoke(prompt)
        doc_type = response.content.strip().upper()
        # Nettoyage au cas où le LLM fait des phrases
        doc_type = "".join([c for c in doc_type if c.isalnum() or c == "_"])
        return doc_type if doc_type else "INCONNU"
    except Exception as e:
        print(f"Erreur classification IA : {e}")
        return "INCONNU"

def simple_text_splitter(text, chunk_size=500, overlap=50):
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i + chunk_size])
    return chunks

def ingest_pdfs(pdf_dir="./data/pdfs"):
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_or_create_collection(name="pdf_rag_collection")
    
    pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf"))
    
    if not pdf_files:
        print(f"Aucun PDF trouvé dans {pdf_dir}.")
        return

    for pdf_path in pdf_files:
        filename = Path(pdf_path).name
        print(f"\nTraitement du fichier : {filename}...")
        
        text = extract_text_from_pdf(pdf_path)
        if not text.strip():
            print(f"-> Document vide ou illisible.")
            continue
            
        # 1. Classification automatique du type de document par l'IA
        doc_type = classify_document_type(text)
        print(f"-> Type détecté par l'IA : {doc_type}")
        
        # 2. Découpage en chunks
        chunks = simple_text_splitter(text, chunk_size=600, overlap=100)
        ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
        
        # 3. Métadonnées enrichies (Nom + Type détecté)
        metadatas = [
            {
                "source": filename,
                "doc_type": doc_type,
                "chunk_index": i
            } 
            for i in range(len(chunks))
        ]
        
        collection.add(documents=chunks, ids=ids, metadatas=metadatas)
        print(f"-> {len(chunks)} chunks insérés avec succès.")

if __name__ == "__main__":
    os.makedirs("./data/pdfs", exist_ok=True)
    ingest_pdfs()