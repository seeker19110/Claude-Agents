from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.state import AgentState
from src.config import settings
from pydantic import BaseModel, Field
from typing import Literal
import os

# --- 1. RAG Agent ---
def rag_agent_node(state: AgentState):
    messages = state.get("messages", [])
    errors = state.get("errors", [])
    
    last_user_msg = [m for m in messages if isinstance(m, HumanMessage)][-1]
    
    # If there are errors, it means the reviewer rejected our previous attempt
    if errors:
        response_text = f"[RAG Agent] Đã sửa lỗi theo yêu cầu của Reviewer: '{errors[-1]}'. Đã trích xuất lại thông tin an toàn."
    else:
        response_text = f"[RAG Agent] Dựa trên cơ sở dữ liệu nội bộ, thông tin liên quan đến '{last_user_msg.content}' là: ... (Mock Data)."

    response = AIMessage(content=response_text, name="RagAgent")
    
    return {
        "messages": [response], 
        "sender": "rag_agent",
        "context": {"rag_status": "success", "docs_retrieved": 5}
    }

# --- 2. Tool Agent ---
def tool_agent_node(state: AgentState):
    messages = state.get("messages", [])
    errors = state.get("errors", [])
    last_user_msg = [m for m in messages if isinstance(m, HumanMessage)][-1]
    
    if errors:
        response_text = f"[Tool Agent] Đã thử lại hành động sau khi Reviewer báo lỗi: '{errors[-1]}'. Thành công."
    else:
        response_text = f"[Tool Agent] Đã thực thi hành động tương ứng với yêu cầu: '{last_user_msg.content}'."
        
    response = AIMessage(content=response_text, name="ToolAgent")
    return {
        "messages": [response], 
        "sender": "tool_agent",
        "context": {"tool_executed": True}
    }

# --- 3. Reviewer Agent ---
def reviewer_agent_node(state: AgentState):
    messages = state.get("messages", [])
    last_msg = messages[-1]
    
    # Mock logic: If the user request had "thử lỗi", we reject the first time
    # Check if there's already an error to avoid infinite loops
    has_errors = len(state.get("errors", [])) > 0
    is_test_error = any("thử lỗi" in m.content.lower() for m in messages if isinstance(m, HumanMessage))
    
    if is_test_error and not has_errors:
        # Simulate a rejection
        response = AIMessage(content=f"[Reviewer Agent] TỪ CHỐI: Kết quả có dấu hiệu rủi ro. Yêu cầu làm lại.", name="ReviewerAgent")
        return {
            "messages": [response],
            "errors": ["Nội dung chứa thông tin không an toàn, vui lòng kiểm tra lại."]
        }
    else:
        # Approve
        response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT: Đã kiểm duyệt kết quả hợp lệ.", name="ReviewerAgent")
        return {"messages": [response]}

# --- 4. Supervisor Agent ---
class RouteResponse(BaseModel):
    next: Literal["FINISH", "rag_agent", "tool_agent"] = Field(description="The next agent to route to, or FINISH.")

def supervisor_node(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return {"next": "FINISH"}
        
    last_msg = messages[-1]
    
    if getattr(last_msg, "name", "") == "ReviewerAgent":
        next_agent = "FINISH"
    else:
        content = last_msg.content.lower()
        if "tìm kiếm" in content or "tài liệu" in content or "kiến thức" in content:
            next_agent = "rag_agent"
        elif "thực hiện" in content or "hành động" in content or "api" in content or "thử lỗi" in content:
            next_agent = "tool_agent"
        else:
            next_agent = "FINISH"
            
    return {"next": next_agent}
