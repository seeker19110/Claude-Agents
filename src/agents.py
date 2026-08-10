from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.state import AgentState
from pydantic import BaseModel, Field
from typing import Literal
import os

# --- 1. RAG Agent ---
def rag_agent_node(state: AgentState):
    messages = state.get("messages", [])
    last_user_msg = [m for m in messages if isinstance(m, HumanMessage)][-1]
    
    response = AIMessage(
        content=f"[RAG Agent] Dựa trên cơ sở dữ liệu nội bộ, thông tin liên quan đến '{last_user_msg.content}' là: ... (Mock Data: Hệ thống đang vận hành ổn định).",
        name="RagAgent"
    )
    return {"messages": [response]}

# --- 2. Tool Agent ---
def tool_agent_node(state: AgentState):
    messages = state.get("messages", [])
    last_user_msg = [m for m in messages if isinstance(m, HumanMessage)][-1]
    
    response = AIMessage(
        content=f"[Tool Agent] Đã thực thi hành động tương ứng với yêu cầu: '{last_user_msg.content}'. (Mock: API call thành công).",
        name="ToolAgent"
    )
    return {"messages": [response]}

# --- 3. Reviewer Agent ---
def reviewer_agent_node(state: AgentState):
    messages = state.get("messages", [])
    
    response = AIMessage(
        content=f"[Reviewer Agent] Đã kiểm duyệt kết quả: Hợp lệ.",
        name="ReviewerAgent"
    )
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
        elif "thực hiện" in content or "hành động" in content or "api" in content:
            next_agent = "tool_agent"
        else:
            next_agent = "FINISH"
            
    return {"next": next_agent}
