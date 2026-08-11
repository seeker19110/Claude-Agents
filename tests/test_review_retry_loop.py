"""Vòng lặp tự sửa lỗi phải CÓ HẠN MỨC nhưng vẫn kiểm duyệt thật ở mọi lần thử.

Regression cho hành vi cũ: hễ state đã có lỗi là Reviewer tự động PHÊ DUYỆT
("auto-pass") nhằm thoát vòng lặp vô tận — nghĩa là bản sửa lần hai không bao giờ
được kiểm duyệt, và người dùng nhận được chữ "PHÊ DUYỆT" cho một kết quả chưa ai xem.
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src import agents
from src.config import settings


class _StubReviewer:
    """Giả lập LLM Reviewer luôn trả về một quyết định định sẵn."""

    def __init__(self, decision, reason=""):
        self._result = agents.ReviewResponse(decision=decision, reason=reason)

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        return self._result


@pytest.fixture
def reject_llm(monkeypatch):
    monkeypatch.setattr(agents, "get_llm", lambda role=None: _StubReviewer("REJECT", "Thiếu trích dẫn TCVN."))


@pytest.fixture
def approve_llm(monkeypatch):
    monkeypatch.setattr(agents, "get_llm", lambda role=None: _StubReviewer("APPROVE"))


def _state(retry_count=0, messages=None):
    return {
        "messages": messages or [HumanMessage(content="Tính tải lạnh phòng 30m2"),
                                 AIMessage(content="Tải lạnh khoảng 3kW.", name="MechanicalAgent")],
        "errors": [],
        "retry_count": retry_count,
    }


def test_first_rejection_increments_retry_and_sets_error(reject_llm):
    result = agents.reviewer_agent_node(_state(retry_count=0))
    assert result["retry_count"] == 1
    assert result["errors"] == ["Thiếu trích dẫn TCVN."]
    assert "TỪ CHỐI" in result["messages"][0].content


def test_retried_work_is_still_reviewed_not_auto_approved(reject_llm):
    """Lần thử thứ hai vẫn phải bị TỪ CHỐI nếu thật sự chưa đạt (trước đây auto-pass)."""
    result = agents.reviewer_agent_node(_state(retry_count=1))
    assert "TỪ CHỐI" in result["messages"][0].content
    assert result["retry_count"] == 2


def test_loop_stops_honestly_at_retry_limit(reject_llm):
    """Chạm trần thì DỪNG, và phải nói rõ là CHƯA ĐẠT — không được báo 'PHÊ DUYỆT'."""
    result = agents.reviewer_agent_node(_state(retry_count=settings.max_review_retries))
    content = result["messages"][0].content
    assert "CHƯA ĐẠT" in content
    assert "PHÊ DUYỆT" not in content
    assert result["errors"] == []      # xóa lỗi để Supervisor kết thúc, không lặp tiếp
    assert result["retry_count"] == 0


def test_approval_resets_retry_counter(approve_llm):
    result = agents.reviewer_agent_node(_state(retry_count=1))
    assert "PHÊ DUYỆT" in result["messages"][0].content
    assert result["retry_count"] == 0


def test_reviewer_error_does_not_claim_approval(monkeypatch):
    """Lỗi kết nối LLM không được ngầm biến thành 'đã duyệt' (fail-open)."""
    class _Boom:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            raise RuntimeError("network down")

    monkeypatch.setattr(agents, "get_llm", lambda role=None: _Boom())
    result = agents.reviewer_agent_node(_state())
    content = result["messages"][0].content
    assert "CHƯA được kiểm duyệt" in content
    assert "PHÊ DUYỆT" not in content


# --- Chặn trả lời suông bằng CẤU TRÚC thay vì blacklist chuỗi ---

def test_deliverable_task_without_tool_call_is_rejected(reject_llm):
    """Yêu cầu bóc khối lượng mà chưa gọi tool tạo file nào thì phải bị từ chối,
    kể cả khi agent diễn đạt bằng câu chữ hoàn toàn mới (blacklist cũ sẽ lọt)."""
    state = {
        "messages": [
            HumanMessage(content="Bóc khối lượng bản vẽ tang1.dxf giúp tôi"),
            AIMessage(content="Về nguyên tắc, ta nên phân loại thiết bị theo từng hệ rồi tổng hợp lại.",
                      name="QSAgent"),
        ],
        "errors": [],
        "retry_count": 0,
    }
    result = agents.reviewer_agent_node(state)
    assert "TỪ CHỐI" in result["messages"][0].content
    assert "auto_quantity_takeoff" in result["errors"][0]


def test_deliverable_task_with_tool_call_passes_structural_check(approve_llm):
    """Đã thực sự gọi tool xuất Excel thì không bị chặn bởi luật chống nói suông."""
    tool_msg = AIMessage(content="", name="QSAgent")
    tool_msg.tool_calls = [{"name": "auto_quantity_takeoff", "args": {}, "id": "1"}]
    state = {
        "messages": [
            HumanMessage(content="Bóc khối lượng bản vẽ tang1.dxf"),
            tool_msg,
            AIMessage(content="Đã xuất file bao_cao_du_toan.xlsx với 12 hạng mục.", name="QSAgent"),
        ],
        "errors": [],
        "retry_count": 0,
    }
    result = agents.reviewer_agent_node(state)
    assert "PHÊ DUYỆT" in result["messages"][0].content


def test_pure_consulting_question_is_not_forced_to_produce_a_file(approve_llm):
    """Câu hỏi tư vấn thuần túy không đòi file thì không được áp luật xuất Excel."""
    state = {
        "messages": [
            HumanMessage(content="Tiêu chuẩn nào quy định độ dốc ống thoát nước?"),
            AIMessage(content="Theo TCVN 4474, độ dốc tối thiểu là 1/D.", name="PlumbingAgent"),
        ],
        "errors": [],
        "retry_count": 0,
    }
    result = agents.reviewer_agent_node(state)
    assert "PHÊ DUYỆT" in result["messages"][0].content
