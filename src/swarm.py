from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
import operator

# Định nghĩa State dùng chung cho Bầy đàn
class SwarmState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    current_agent: str
    takeoff_files: list[str]

# Công cụ Handoff (Giao việc chéo)
def delegate_to_electrical(query: str):
    """Giao việc cho Agent Điện (Electrical) xử lý các vấn đề cáp/tủ điện."""
    return f"Đã chuyển yêu cầu '{query}' cho Kỹ sư Điện."

def delegate_to_mechanical(query: str):
    """Giao việc cho Agent Cơ (Mechanical) xử lý các vấn đề ống gió/điều hòa."""
    return f"Đã chuyển yêu cầu '{query}' cho Kỹ sư Cơ Điện."

def delegate_to_qs(query: str):
    """Giao việc cho QS Auditor kiểm tra khối lượng và chi phí."""
    return f"Đã chuyển yêu cầu '{query}' cho Bộ phận QS."

# Agent Node giả lập cho Swarm
def mechanical_swarm_node(state: SwarmState):
    """Kỹ sư Cơ có thể tự phân tích, hoặc nếu thấy thiếu dây điện, sẽ tự gọi delegate_to_electrical."""
    # Logic LangChain Agent thực tế sẽ nằm ở đây
    return {"current_agent": "mechanical"}

def electrical_swarm_node(state: SwarmState):
    return {"current_agent": "electrical"}

def qs_auditor_swarm_node(state: SwarmState):
    return {"current_agent": "qs"}

# Xây dựng Đồ thị Swarm Mở (Không chạy tuần tự tĩnh)
swarm_graph = StateGraph(SwarmState)

swarm_graph.add_node("mechanical", mechanical_swarm_node)
swarm_graph.add_node("electrical", electrical_swarm_node)
swarm_graph.add_node("qs_auditor", qs_auditor_swarm_node)

# Trong mô hình Swarm, mỗi node có thể dẫn tới TẤT CẢ các node khác
# Điều hướng dựa trên tool `delegate_to_xxx` mà LLM vừa gọi.
def route_swarm(state: SwarmState):
    # Dummy logic: Nếu LLM gọi delegate_to_electrical, return "electrical"
    return END # Mặc định kết thúc nếu không giao việc tiếp

swarm_graph.add_conditional_edges("mechanical", route_swarm)
swarm_graph.add_conditional_edges("electrical", route_swarm)
swarm_graph.add_conditional_edges("qs_auditor", route_swarm)

swarm_graph.add_edge(START, "mechanical")

swarm_app = swarm_graph.compile()
