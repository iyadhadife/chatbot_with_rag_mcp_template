from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

class HistoryManager:
    def __init__(self, system_message):
        self.chat_history = [system_message]

    def add_user_message(self, content: str):
        self.chat_history.append(HumanMessage(content=content))

    def add_ai_message(self, content: str):
        self.chat_history.append(AIMessage(content=content))

    def add_tool_message(self, content: str, tool_call_id: str):
        self.chat_history.append(ToolMessage(content=content, tool_call_id=tool_call_id))

    def rollback_last(self):
        """Retire le dernier message en cas d'erreur pour garder un historique propre."""
        if len(self.chat_history) > 1:
            self.chat_history.pop()

    def get_history(self):
        return self.chat_history