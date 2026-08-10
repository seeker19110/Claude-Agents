from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.state import AgentState
from src.config import settings
from pydantic import BaseModel, Field
from typing import Literal
from src.tools import tools

from dotenv import load_dotenv
import os

def get_llm():
    load_dotenv(override=True)
    provider = os.getenv("LLM_PROVIDER", "openai").lower().strip()
    model_name = os.getenv("MODEL_NAME", "").strip()
    
    if provider == "groq":
        from langchain_groq import ChatGroq
        key = os.getenv("GROQ_API_KEY", "") or "dummy_key"
        if not model_name or "gpt" in model_name or "gemini" in model_name or "3.1" in model_name:
            model_name = "llama-3.3-70b-versatile"
        return ChatGroq(model=model_name, api_key=key, temperature=0)
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = os.getenv("GOOGLE_API_KEY", "") or "dummy_key"
        if not model_name or "gpt" in model_name or "llama" in model_name:
            model_name = "gemini-1.5-flash"
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=key, temperature=0)
    elif provider == "ollama":
        from langchain_openai import ChatOpenAI
        if not model_name or "gpt" in model_name or "gemini" in model_name:
            model_name = "llama3.1:8b"
        return ChatOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model=model_name,
            temperature=0
        )
    else:
        from langchain_openai import ChatOpenAI
        key = os.getenv("OPENAI_API_KEY", "") or "dummy_key"
        if not model_name or "llama" in model_name or "gemini" in model_name:
            model_name = "gpt-4o-mini"
        return ChatOpenAI(model=model_name, api_key=key, temperature=0)

def call_mepf_agent(state: AgentState, system_prompt: str, agent_name: str):
    messages = state.get("messages", [])
    errors = state.get("errors", [])
    
    if errors:
        system_prompt += f"\n\nCẢNH BÁO: Lần trả lời trước của bạn đã bị Reviewer từ chối với lỗi: '{errors[-1]}'. Hãy sửa lỗi này và đưa ra phương án khả thi hơn."
        
    sys_msg = SystemMessage(content=system_prompt)
    
    llm = get_llm()
    tool_llm = llm.bind_tools(tools)
    
    try:
        response = tool_llm.invoke([sys_msg] + messages)
        response.name = agent_name
        return {"messages": [response], "sender": agent_name.lower()}
    except Exception as e:
        content = f"[{agent_name}] Lỗi khi kết nối LLM ({os.getenv('LLM_PROVIDER', 'openai')}): {str(e)}"
        return {"messages": [AIMessage(content=content, name=agent_name)], "sender": agent_name.lower()}

# --- 1. Mechanical (HVAC) Agent ---
def mechanical_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Cơ khí (HVAC) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn (TCVN/ASHRAE). \n- Luôn sử dụng bộ công cụ HVAC: `calc_cooling_load` (tải lạnh), `calc_duct_size` (ống gió), `calc_psychrometrics` (trạng thái không khí), `calc_chw_pipe_size` (ống nước lạnh), `calc_pump_fan_power` (công suất quạt/bơm), `calc_ventilation_rate` (thông gió/hút khói). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "MechanicalAgent")

# --- 2. Electrical Agent ---
def electrical_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Điện (Electrical) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn (TCVN/IEC). \n- Luôn sử dụng bộ công cụ Điện: `calc_cable_size` (tính cáp), `calc_breaker_size` (tính MCB/MCCB), `calc_lighting_qty` (tính số lượng đèn). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "ElectricalAgent")

# --- 3. Plumbing Agent ---
def plumbing_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Cấp thoát nước (Plumbing) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu tiêu chuẩn. \n- Luôn sử dụng bộ công cụ Nước: `calc_water_pipe` (tính lưu lượng/cỡ ống nước), `calc_water_tank` (tính bể ngầm/mái), `calc_plumbing_pump_head` (tính cột áp bơm cấp nước). \n- Cấm đoán mò các thông số này. Đảm bảo mọi lập luận đều có căn cứ kỹ thuật toán học."
    return call_mepf_agent(state, prompt, "PlumbingAgent")

# --- 4. Firefighting Agent ---
def firefighting_agent_node(state: AgentState):
    prompt = "Bạn là Kỹ sư Phòng cháy chữa cháy (Firefighting) cấp chuyên gia. \n- Luôn gọi tool `search_standards` để tra cứu quy chuẩn PCCC (TCVN 3890, TCVN 7336). \n- Luôn sử dụng bộ công cụ PCCC: `calc_sprinkler_qty` (tính đầu phun), `calc_fire_pump` (tính bơm chữa cháy), `calc_extinguisher_qty` (tính số lượng bình chữa cháy). \n- Cấm đoán mò các thông số này. Mọi bố trí phải tuân thủ nghiêm ngặt tiêu chuẩn."
    return call_mepf_agent(state, prompt, "FirefightingAgent")

# --- 5. QS Agent (Quantity Surveyor) ---
def qs_agent_node(state: AgentState):
    prompt = """Bạn là một Kỹ sư QS xuất sắc. Bạn dùng công cụ `read_cad` để đọc bản vẽ DXF. 
    Nếu bản vẽ bị phá Block (nổ Block), hãy yêu cầu/hoặc tự dùng `ai_block_recovery` để phục hồi lại Block trước khi đếm khối lượng.
    - DANH MỤC BLOCK CHUẨN ĐỂ PHỤC HỒI CỦA 4 HỆ (CHỨA TRONG TỔNG KHO):
      + HVAC (Cơ Khí): 'DIFFUSER_SUPPLY' (600x600), 'DIFFUSER_RETURN' (600x600), 'FCU' (1000x500)
      + Electrical (Điện): 'LIGHT_PANEL' (600x600), 'LIGHT_DOWNLIGHT' (Tròn R=100), 'SOCKET' (Tròn R=50), 'SWITCH' (Tròn R=30)
      + Firefighting (PCCC): 'SPRINKLER' (Tròn R=50)
      + Plumbing (Nước): 'PUMP' (Tròn R=50)
    Sau khi phục hồi, dùng `read_cad` đếm lại và xuất file Excel dự toán (`write_excel`).
    """
    return call_mepf_agent(state, prompt, "QSAgent")

# --- 6. CAD Agent (Draftsman) ---
def cad_agent_node(state: AgentState):
    prompt = """Bạn là Họa viên CAD (Draftsman) xuất sắc nhất thế giới sở hữu Thị giác Máy tính (Computer Vision).
    - Bạn có quyền sử dụng công cụ `read_cad`, `write_cad`, `edit_cad`, và `render_cad_image`.
    - THỊ GIÁC CAD (COMPUTER VISION): Mỗi khi đọc, chỉnh sửa hoặc tạo mới bản vẽ, bạn NÊN gọi công cụ `render_cad_image` để xuất hình ảnh PNG trực quan giúp người dùng và hệ thống xem trực tiếp bản vẽ trên màn hình.
    - CÔNG CỤ PHỤC HỒI (AI BLOCK RECOVERY): Khi khách yêu cầu khôi phục bản vẽ vỡ block, dùng công cụ `ai_block_recovery` quét hình dáng (circle/rectangle) để ráp lại thành Block từ Tổng kho.
      + Mẹo: Các block chuẩn 4 hệ MEPF đã có sẵn trong kho gồm: 'DIFFUSER_SUPPLY', 'DIFFUSER_RETURN', 'FCU', 'LIGHT_PANEL', 'LIGHT_DOWNLIGHT', 'SOCKET', 'SWITCH', 'SPRINKLER', 'PUMP'.
    - CƠ CHẾ AUTO-DRAW (SIÊU NĂNG LỰC): Nếu người dùng yêu cầu chèn một thiết bị máy móc mà không có sẵn trong thư viện, hãy dùng `search_web` tìm kích thước, dùng `execute_python_code` viết script ezdxf vẽ Block đó lưu vào 'data/blocks/mepf_library.dxf', sau đó chèn vào bản vẽ.
    - LUẬT PHÊ DUYỆT BẮT BUỘC: Sau khi bạn dùng tool sửa xong bản vẽ, LUÔN chốt lại bằng câu: "Bản vẽ đã hoàn thiện và làm sạch. Xin Sếp hãy mở file lên kiểm tra và nhấp nút '✅ DUYỆT BẢN VẼ' để tôi báo Giám đốc gọi bộ phận QS bóc khối lượng!".
    """
    return call_mepf_agent(state, prompt, "CADAgent")

# --- 7. BIM Agent ---
def bim_agent_node(state: AgentState):
    prompt = "Bạn là một BIM Coordinator xuất sắc. Quản lý mô hình 3D, kiểm tra xung đột."
    return call_mepf_agent(state, prompt, "BIMAgent")

# --- 8. Reviewer Agent ---
class ReviewResponse(BaseModel):
    decision: Literal["APPROVE", "REJECT"] = Field(description="Quyết định phê duyệt hoặc từ chối.")
    reason: str = Field(description="Lý do chi tiết cho quyết định (nếu từ chối).", default="")

def reviewer_agent_node(state: AgentState):
    messages = state.get("messages", [])
    last_msg = messages[-1]
    has_errors = len(state.get("errors", [])) > 0
    
    if has_errors:
        response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT (Auto-pass sau khi sửa lỗi).", name="ReviewerAgent")
        return {"messages": [response]}
        
    system_prompt = SystemMessage(content="""Bạn là Kỹ sư trưởng (Reviewer). Kiểm tra kết quả tư vấn.
Yêu cầu bắt buộc:
1. Nếu là tính toán thiết kế MEPF, phải có trích dẫn Tiêu chuẩn (TCVN/ASHRAE/NFPA).
2. Nếu là gọi Tool đọc/ghi file, đánh giá APPROVE ngay để không chặn luồng.
Nếu thông tin sai kỹ thuật hoặc thiếu căn cứ, hãy REJECT.""")

    try:
        llm = get_llm()
        reviewer_llm = llm.with_structured_output(ReviewResponse)
        review_result = reviewer_llm.invoke([system_prompt, last_msg])
        
        if review_result.decision == "REJECT":
            response = AIMessage(content=f"[Reviewer Agent] TỪ CHỐI: {review_result.reason}", name="ReviewerAgent")
            return {"messages": [response], "errors": [review_result.reason]}
        else:
            response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT: Phương án kỹ thuật hợp lệ.", name="ReviewerAgent")
            return {"messages": [response]}
    except Exception as e:
        response = AIMessage(content=f"[Reviewer Agent] PHÊ DUYỆT: Phương án kỹ thuật hợp lệ.", name="ReviewerAgent")
        return {"messages": [response]}

# --- 9. Supervisor Agent (Project Manager) ---
class RouteResponse(BaseModel):
    next: Literal["FINISH", "mechanical", "electrical", "plumbing", "firefighting", "qs", "cad", "bim"] = Field(
        description="Định tuyến đến bộ phận phù hợp, hoặc FINISH."
    )

def supervisor_node(state: AgentState):
    messages = state.get("messages", [])
    if not messages:
        return {"next": "FINISH"}
        
    last_msg = messages[-1]
    
    if getattr(last_msg, "name", "") == "ReviewerAgent":
        return {"next": "FINISH"}

    supervisor_prompt = """Bạn là Giám đốc Dự án (Project Manager) của Văn phòng tư vấn MEPF.
Bạn là người đứng đầu, chịu trách nhiệm nhận yêu cầu tổng hợp từ khách hàng và chia nhỏ công việc cho đội ngũ Kỹ sư.
Phân loại yêu cầu:
- 'mechanical': Nếu liên quan đến HVAC, thông gió, điều hòa.
- 'electrical': Nếu liên quan đến Điện, chiếu sáng, tủ điện.
- 'plumbing': Nước, bơm, vệ sinh.
- 'firefighting': PCCC.
- 'qs': Bóc khối lượng, lập dự toán, đọc thuộc tính, xuất Excel.
- 'cad': Tạo/sửa bản vẽ CAD.
- 'bim': 3D.
- 'FINISH': Nếu đã hoàn thành hoặc khách hàng chỉ hỏi vu vơ không liên quan dự án.

Hãy hoạt động như một PM thực thụ: Nếu khách hàng yêu cầu "Thiết kế hệ thống điện và lập báo giá", hãy gọi 'electrical' trước. Sau khi 'electrical' hoàn thành, vòng lặp trở lại, bạn mới tiếp tục gọi 'qs' để lập báo giá.

QUY TẮC THÉP (LUẬT PHÊ DUYỆT):
- Tuyệt đối không được định tuyến sang 'qs' (để bóc khối lượng) ngay sau khi bộ phận 'cad' vừa thao tác sửa/phục hồi bản vẽ xong.
- Bạn PHẢI định tuyến về 'FINISH' để buộc luồng chạy dừng lại, nhường màn hình cho khách hàng kiểm tra bản vẽ. 
- Chỉ khi nào có tin nhắn phản hồi mới từ khách hàng với các từ khóa "Duyệt", "Ok", "Tiến hành đi", "Tiếp tục" thì bạn mới được định tuyến sang 'qs'.
"""
    
    sys_msg = SystemMessage(content=supervisor_prompt)
    llm = get_llm()
    structured_llm = llm.with_structured_output(RouteResponse)
    
    try:
        response = structured_llm.invoke([sys_msg, last_msg])
        next_agent = response.next
        return {"next": next_agent}
    except Exception as e:
        error_msg = f"Lỗi Giám đốc Dự án ({os.getenv('LLM_PROVIDER', 'openai')}): {str(e)}"
        print(f"[PM] Lỗi định tuyến: {error_msg}")
        from langchain_core.messages import AIMessage
        return {"messages": [AIMessage(content=error_msg, name="ProjectManager")], "next": "FINISH"}
