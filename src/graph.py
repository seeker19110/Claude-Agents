from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from src.state import AgentState
from src.agents import supervisor_node, rag_agent_node, tool_agent_node, reviewer_agent_node

# 1. Initialize the graph
workflow = StateGraph(AgentState)

# 2. Add the nodes
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("rag_agent", rag_agent_node)
workflow.add_node("tool_agent", tool_agent_node)
workflow.add_node("reviewer_agent", reviewer_agent_node)

# 3. Add edges
workflow.add_edge(START, "supervisor")
workflow.add_edge("rag_agent", "reviewer_agent")
workflow.add_edge("tool_agent", "reviewer_agent")

# Logic to route from reviewer
def reviewer_router(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return "supervisor"
        
    last_msg = messages[-1]
    
    # If the reviewer rejected it, route back to sender
    if getattr(last_msg, "name", "") == "ReviewerAgent" and "TỪ CHỐI" in last_msg.content:
        sender = state.get("sender", "supervisor")
        if sender in ["rag_agent", "tool_agent"]:
            return sender
            
    # If no errors or approved, route to supervisor to finish
    return "supervisor"

workflow.add_conditional_edges(
    "reviewer_agent",
    reviewer_router,
    {
        "rag_agent": "rag_agent",
        "tool_agent": "tool_agent",
        "supervisor": "supervisor"
    }
)

workflow.add_conditional_edges(
    "supervisor",
    lambda state: state.get("next", "FINISH"),
    {
        "rag_agent": "rag_agent",
        "tool_agent": "tool_agent",
        "FINISH": END
    }
)

# 4. Compile the graph
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
