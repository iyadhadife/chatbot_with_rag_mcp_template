import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
from dotenv import load_dotenv
import os

async def envoyer_requete():
    url = "http://localhost:8000/sse" # Vérifie bien le port !
    
    # COPIE LE TOKEN DEPUIS TON TERMINAL ICI
    load_dotenv()
    # token = os.getenv('TOKEN_FOR_MCP_SERVER')
    
    # headers = {
    #     "Authorization": f"Bearer {token}"
    # }

    print(f"🌐 Connexion à l'inspecteur...")
    try:
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Appel de ton outil
                result = await session.call_tool(
                    "interroger_base_connaissance", 
                    arguments={"question": "Comment vérifier le swap ?"}
                )
                
                print("\n[RÉPONSE DU RAG] :")
                print(result.content[0].text)
    except Exception as e:
        print(f"Erreur : {e}")

if __name__ == "__main__":
    asyncio.run(envoyer_requete())