from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.state import AgentState
from src.config import settings
from pydantic import BaseModel, Field
from typing import Literal
from src.tools import tools

# Initialize LLM
llm = ChatOpenAI(model=settings.model_name, api_key=settings.openai_api_key, temperature=0)

# Bind tools to LLM for the Tool Agent
tool_llm = llm.bind_tools(tools)

# --- 1. Supervisor Agent ---
class RouteResponse(BaseModel):
    next: Literal["FINISH", "rag_agent", "tool_agent"] = Field(description="The next agent to route to, or FINISH.")

def supervisor_node(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return {"next": "FINISH"}
        
    last_msg = messages[-1]
    
    # Nếu tin nhắn cuối cùng là từ Reviewer, thì kết thúc
    if getattr(last_msg, "name", "") == "ReviewerAgent":
        return {"next": "FINISH"}
    
    # Sử dụng LLM để ra quyết định điều hướng
    system_prompt = SystemMessage(content="""Bạn là một nhạc trưởng điều phối công việc.
Nhiệm vụ của bạn là phân tích yêu cầu của người dùng và điều hướng đến một trong các agent sau:
- 'rag_agent': Nếu người dùng hỏi về kiến thức, tài liệu nội bộ, chính sách, hoặc cần tra cứu thông tin tĩnh.
- 'tool_agent': Nếu người dùng yêu cầu thực hiện một hành động (như tìm kiếm web, tính toán, gửi API).
- 'FINISH': Nếu không cần làm gì thêm hoặc đã hoàn thành.
""")
    
    # Chỉ truyền system prompt và tin nhắn cuối của user để Supervisor quyết định
    # Tránh truyền toàn bộ lịch sử nếu không cần thiết để giảm token
    invoke_msgs = [system_prompt, last_msg]
    
    supervisor_llm = llm.with_structured_output(RouteResponse)
    response = supervisor_llm.invoke(invoke_msgs)
    
    return {"next": response.next}

# --- 2. RAG Agent ---
def rag_agent_node(state: AgentState):
    messages = state.get("messages", [])
    errors = state.get("errors", [])
    
    system_prompt_content = """Bạn là một chuyên gia RAG (Retrieval-Augmented Generation).
Nhiệm vụ của bạn là trả lời câu hỏi của người dùng dựa trên cơ sở tri thức (MOCK: hiện tại hãy giả định bạn có quyền truy cập vào CSDL nội bộ và hãy tự bịa ra một câu trả lời hợp lý, chuyên nghiệp như thể bạn vừa tra cứu tài liệu thật).
Luôn giữ thái độ lịch sự và chuyên nghiệp."""

    if errors:
        system_prompt_content += f"\n\nCẢNH BÁO: Lần trả lời trước của bạn đã bị Reviewer từ chối với lỗi: '{errors[-1]}'. Hãy sửa lỗi này trong câu trả lời mới."

    invoke_msgs = [SystemMessage(content=system_prompt_content)] + messages
    
    response = llm.invoke(invoke_msgs)
    response.name = "RagAgent"
    
    return {
        "messages": [response], 
        "sender": "rag_agent",
        "context": {"rag_status": "success", "docs_retrieved": 1} # Mock context
    }

# --- 3. Tool Agent ---
def tool_agent_node(state: AgentState):
    messages = state.get("messages", [])
    errors = state.get("errors", [])
    
    system_prompt_content = """Bạn là một AI Assistant có khả năng sử dụng các công cụ.
Hãy phân tích yêu cầu và sử dụng công cụ phù hợp để hoàn thành nhiệm vụ."""
    
    if errors:
        system_prompt_content += f"\n\nCẢNH BÁO: Lần thực thi trước của bạn đã bị Reviewer từ chối với lỗi: '{errors[-1]}'. Hãy sửa lỗi này."

    invoke_msgs = [SystemMessage(content=system_prompt_content)] + messages
    
    response = tool_llm.invoke(invoke_msgs)
    response.name = "ToolAgent"
    
    return {
        "messages": [response], 
        "sender": "tool_agent",
        "context": {"tool_called": bool(response.tool_calls)}
    }

# --- 4. Reviewer Agent ---
class ReviewResponse(BaseModel):
    decision: Literal["APPROVE", "REJECT"] = Field(description="Quyết định phê duyệt hoặc từ chối.")
    reason: str = Field(description="Lý do chi tiết cho quyết định (nếu từ chối).", default="")

def reviewer_agent_node(state: AgentState):
    messages = state.get("messages", [])
    last_msg = messages[-1]
    has_errors = len(state.get("errors", [])) > 0
    
    # Nếu đã từng lỗi 1 lần, duyệt luôn để tránh lặp vô hạn (chỉ là rule tạm thời cho demo)
    if has_errors:
        response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT (Auto-pass sau khi sửa lỗi): Nội dung đã được cải thiện.", name="ReviewerAgent")
        return {"messages": [response]}
        
    system_prompt = SystemMessage(content="""Bạn là một Reviewer Agent. Nhiệm vụ của bạn là kiểm tra kết quả của các Agent khác (như RagAgent, ToolAgent).
Tiêu chí đánh giá:
1. Thông tin không được chứa ngôn từ độc hại, xúc phạm.
2. Nếu kết quả là câu trả lời cho người dùng, nó phải mạch lạc và đúng trọng tâm.
3. Nếu nội dung có vẻ không an toàn hoặc chứa thông tin giả mạo trắng trợn, hãy REJECT.

Hãy đánh giá và trả về quyết định.""")

    reviewer_llm = llm.with_structured_output(ReviewResponse)
    review_result = reviewer_llm.invoke([system_prompt, last_msg])
    
    if review_result.decision == "REJECT":
        response = AIMessage(content=f"[Reviewer Agent] TỪ CHỐI: {review_result.reason}", name="ReviewerAgent")
        return {
            "messages": [response],
            "errors": [review_result.reason]
        }
    else:
        response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT: Đã kiểm duyệt kết quả hợp lệ.", name="ReviewerAgent")
        return {"messages": [response]}
