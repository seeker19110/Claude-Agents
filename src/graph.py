from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from src.state import AgentState
from src.agents import supervisor_node, rag_agent_node, tool_agent_node, reviewer_agent_node
from src.tools import tools
from langgraph.prebuilt import ToolNode

# 1. Initialize the graph
workflow = StateGraph(AgentState)

# 2. Add the nodes
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("rag_agent", rag_agent_node)
workflow.add_node("tool_agent", tool_agent_node)
workflow.add_node("tools", ToolNode(tools)) # Thực thi các tool
workflow.add_node("reviewer_agent", reviewer_agent_node)

# 3. Add edges
workflow.add_edge(START, "supervisor")

# RAG agent luôn qua reviewer
workflow.add_edge("rag_agent", "reviewer_agent")

# Logic điều hướng cho Tool Agent
def tool_agent_router(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return "reviewer_agent"
    
    last_msg = messages[-1]
    
    # Nếu có tool calls thì chuyển qua node tools để thực thi
    if getattr(last_msg, "tool_calls", None):
        return "tools"
        
    # Nếu không, chuyển qua reviewer
    return "reviewer_agent"

workflow.add_conditional_edges(
    "tool_agent",
    tool_agent_router,
    {
        "tools": "tools",
        "reviewer_agent": "reviewer_agent"
    }
)

# Sau khi tools chạy xong, quay lại tool_agent để tạo câu trả lời cuối
workflow.add_edge("tools", "tool_agent")

# Logic to route from reviewer
def reviewer_router(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return "supervisor"
        
    last_msg = messages[-1]
    
    # Nếu bị từ chối, trả về cho người gửi ban đầu
    if getattr(last_msg, "name", "") == "ReviewerAgent" and "TỪ CHỐI" in last_msg.content:
        sender = state.get("sender", "supervisor")
        if sender in ["rag_agent", "tool_agent"]:
            return sender
            
    # Nếu pass, về lại supervisor
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

# 4. Compile the graph with memory and interrupt
memory = MemorySaver()
# Thêm interrupt_before=["tools"] để kích hoạt Human-in-the-loop (HITL)
# Nghĩa là trước khi chạy bất kỳ tool nào, hệ thống sẽ tạm dừng để người dùng duyệt.
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["tools"]
)
