from typing import Annotated, Sequence, TypedDict, Any
from langchain_core.messages import BaseMessage
import operator

def update_dict(old_dict: dict, new_dict: dict) -> dict:
    """Merge two dictionaries, updating existing keys."""
    res = old_dict.copy()
    res.update(new_dict)
    return res

class AgentState(TypedDict):
    """The routing state of the multi-agent system."""
    # Messages in the conversation
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # The next node to route to, if decided by supervisor
    next: str
    
    # Shared context dictionary (e.g. extracted variables, metadata)
    context: Annotated[dict[str, Any], update_dict]
    
    # Errors occurred during execution, if any
    errors: Annotated[Sequence[str], operator.add]
    
    # Track the last active worker (e.g. "rag_agent" or "tool_agent") 
    # so Reviewer knows who to send back to if there's an error.
    sender: str
