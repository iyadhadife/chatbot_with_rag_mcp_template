from langchain_core.messages import SystemMessage

def get_system_instructions() -> SystemMessage:
    """Retourne les règles et consignes système pour le comportement de l'assistant."""
    return SystemMessage(content="""Tu es un assistant expert intelligent. 
Tu as accès à des outils de recherche et d'ingestion spécialisés. 
Analyse la question de l'utilisateur et utilise TOUJOURS l'outil le plus adapté.""")