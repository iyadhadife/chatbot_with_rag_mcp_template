import os
import re

from langchain_core.messages import AIMessage, HumanMessage

# Budget d'historique rejoué au modèle (le contexte RAG, lui, n'est jamais rejoué)
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "3"))        # derniers échanges
MAX_HISTORY_CHARS = int(os.getenv("MAX_HISTORY_CHARS", "3000"))     # total
MAX_ANSWER_CHARS  = int(os.getenv("MAX_ANSWER_CHARS", "1200"))      # par réponse rejouée

# Marques d'une question qui dépend de l'échange précédent
_FOLLOWUP_STARTS = ("et ", "mais ", "donc ", "alors ", "pourquoi", "comment ça", "ok ")
_FOLLOWUP_WORDS = re.compile(
    r"\b(il|elle|ils|elles|lui|leur|leurs|son|sa|ses|cela|ça|ca|celui|celle|ceux|"
    r"précédent|précédente|précédents|même|mêmes|autres?|aussi|encore|détail\w*|"
    r"reformul\w*|résum\w*|développ\w*|explique|continue)\b",
    re.IGNORECASE,
)


def is_follow_up(question: str) -> bool:
    """
    Heuristique sans LLM : la question renvoie-t-elle à l'échange précédent ?
    (pronoms, connecteurs, demandes de reformulation, question très courte).
    """
    q = question.strip().lower()
    if len(q.split()) <= 4:
        return True
    return q.startswith(_FOLLOWUP_STARTS) or bool(_FOLLOWUP_WORDS.search(q))


class HistoryManager:
    """
    Historique compact : seuls les échanges (question, réponse finale) sont
    conservés. Les appels d'outils et les passages RAG (volumineux) ne sont
    valables que le temps du tour courant, ils ne sont jamais rejoués.
    L'historique n'est joint au prompt que si la question en dépend.
    """

    def __init__(self, system_message):
        self.system_message = system_message
        self.turns: list[tuple[str, str]] = []

    def reset(self):
        self.turns.clear()

    def add_exchange(self, question: str, answer: str):
        self.turns.append((question, answer))

    def _recent_turns(self) -> list[tuple[str, str]]:
        """Derniers échanges, bornés en nombre et en taille (les plus récents d'abord)."""
        kept, used = [], 0
        for q, a in reversed(self.turns[-MAX_HISTORY_TURNS:]):
            a = a if len(a) <= MAX_ANSWER_CHARS else a[:MAX_ANSWER_CHARS] + "…"
            size = len(q) + len(a)
            if kept and used + size > MAX_HISTORY_CHARS:
                break
            kept.append((q, a))
            used += size
        return list(reversed(kept))

    def build_messages(self, question: str) -> list:
        """Messages du tour : système + historique utile (si besoin) + question."""
        messages = [self.system_message]
        if self.turns and is_follow_up(question):
            for q, a in self._recent_turns():
                messages.append(HumanMessage(content=q))
                messages.append(AIMessage(content=a))
        messages.append(HumanMessage(content=question))
        return messages

    def search_query(self, question: str) -> str:
        """
        Requête de recherche RAG. Une question de suivi (« et son expérience ? »)
        est trop pauvre seule : on la complète avec la question précédente.
        """
        if self.turns and is_follow_up(question):
            return f"{self.turns[-1][0]} {question}"
        return question
