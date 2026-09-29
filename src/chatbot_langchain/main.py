import os
from rag_pipeline.retriever import ChatbotRetriever
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

def run_chatbot():
    print("Initialisation du Retriever pour le Chatbot...")
    retriever = ChatbotRetriever()
    
    # Configuration d'Ollama
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    print(f"Connexion à Ollama sur {ollama_base_url}...")
    
    llm = ChatOllama(
        model="qwen2.5:7b",
        base_url=ollama_base_url,
        temperature=0.1
    )
    
    # Initialisation de l'historique
    chat_history = [
        SystemMessage(content="""Tu es un assistant expert intelligent. 
Tu as accès à plusieurs documents de natures différentes (par exemple un CV et un Devis), étiquetés par leur type et leur source.
Règles strictes :
1. Examine TOUS les blocs de contexte fournis, quelle que soit leur source.
2. Si la question nécessite de combiner des informations provenant à la fois du CV et du Devis, tu DOIS utiliser les deux et faire le lien entre eux.
3. Ne mélange pas les rôles : ce qui appartient au CV concerne le profil/compétences, ce qui appartient au Devis concerne la prestation/projet.
4. Cite toujours le type de document ou le fichier source quand tu donnes une information""")]
    
    print("\n=== Chatbot RAG en Streaming avec Historique (Tapez 'exit' pour quitter) ===")
    
    while True:
        user_query = input("\n\nVous : ")
        if user_query.lower() == 'exit':
            print("Fermeture du chat. Au revoir !")
            break
            
        if not user_query.strip():
            continue
            
        # 1. Récupération du contexte pertinent depuis ChromaDB
        context = retriever.get_context(user_query, n_results=10)
        
        # 2. Construction du prompt enrichi avec le contexte
        prompt_with_context = f"""Contexte pertinent extrait des documents :\n{context}\n\nQuestion de l'utilisateur : {user_query}"""
        
        # Ajout dans l'historique
        chat_history.append(HumanMessage(content=prompt_with_context))
        
        print("\nAssistant : ", end="", flush=True)
        
        full_response = ""
        try:
            # 3. Appel en streaming via LangChain
            for chunk in llm.stream(chat_history):
                print(chunk.content, end="", flush=True)
                full_response += chunk.content
            
            # 4. Enregistrement de la réponse complète dans l'historique
            chat_history.append(AIMessage(content=full_response))
            
        except Exception as e:
            print(f"\nErreur lors de la communication avec Ollama : {e}")
            chat_history.pop() # Nettoyage de l'historique en cas d'échec

if __name__ == "__main__":
    run_chatbot()