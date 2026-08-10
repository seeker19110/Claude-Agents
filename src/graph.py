from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from src.state import AgentState
from src.tools import tools
from src.agents import (
    supervisor_node, mechanical_agent_node, electrical_agent_node,
    plumbing_agent_node, firefighting_agent_node,
    qs_agent_node, cad_agent_node, bim_agent_node,
    reviewer_agent_node
)

# 1. Khởi tạo Graph
workflow = StateGraph(AgentState)

# 2. Thêm các Node cho phòng MEPF, QS, CAD, BIM và Tools
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("mechanical", mechanical_agent_node)
workflow.add_node("electrical", electrical_agent_node)
workflow.add_node("plumbing", plumbing_agent_node)
workflow.add_node("firefighting", firefighting_agent_node)
workflow.add_node("qs", qs_agent_node)
workflow.add_node("cad", cad_agent_node)
workflow.add_node("bim", bim_agent_node)
workflow.add_node("reviewer", reviewer_agent_node)
workflow.add_node("tools", ToolNode(tools))

# 3. Khai báo các Edges
workflow.add_edge(START, "supervisor")

# Hàm điều hướng sau khi Agent xử lý: Có gọi Tool hay lên Reviewer?
def route_after_agent(state: AgentState):
    last_msg = state.get("messages", [])[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return "reviewer"

# Áp dụng điều hướng cho tất cả Agent
agents = ["mechanical", "electrical", "plumbing", "firefighting", "qs", "cad", "bim"]
for agent in agents:
    workflow.add_conditional_edges(
        agent,
        route_after_agent,
        {"tools": "tools", "reviewer": "reviewer"}
    )

# Hàm điều hướng sau khi Tools chạy xong: Trả về Agent đã gọi
def route_after_tools(state: AgentState):
    sender = state.get("sender")
    if sender in agents:
        return sender
    return "supervisor"

workflow.add_conditional_edges("tools", route_after_tools)

# Reviewer phản hồi cho Supervisor
workflow.add_edge("reviewer", "supervisor")

# Supervisor định tuyến luồng
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state.get("next", "FINISH"),
    {
        "mechanical": "mechanical",
        "electrical": "electrical",
        "plumbing": "plumbing",
        "firefighting": "firefighting",
        "qs": "qs",
        "cad": "cad",
        "bim": "bim",
        "FINISH": END
    }
)

# 4. Compile đồ thị với MemorySaver
# Compile đồ thị với MemorySaver
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
