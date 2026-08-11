"""Định tuyến của Supervisor và khớp tên node giữa agents.py <-> graph.py."""
from langchain_core.messages import AIMessage, HumanMessage

from src import agents
from src.state import RESET, append_or_reset


def test_agent_node_key_matches_graph_node_names():
    """Regression: `sender` từng được ghi là 'mechanicalagent' trong khi graph.py so
    khớp với tên node 'mechanical' — không bao giờ khớp, nên kết quả tool bị đẩy lên
    Supervisor thay vì trả về đúng agent đã gọi, và mọi lần TỪ CHỐI đều rơi về 'qs'."""
    from src.graph import agents as graph_node_names

    for agent_name in ["MechanicalAgent", "ElectricalAgent", "PlumbingAgent",
                       "FirefightingAgent", "QSAgent", "CADAgent", "BIMAgent"]:
        assert agents.agent_node_key(agent_name) in graph_node_names


def test_rejection_routes_back_to_the_agent_that_failed():
    state = {
        "messages": [AIMessage(content="[Reviewer Agent] TỪ CHỐI: thiếu căn cứ", name="ReviewerAgent")],
        "sender": "electrical",
    }
    assert agents.supervisor_node(state)["next"] == "electrical"


def test_flow_stops_after_cad_edits_for_human_approval():
    """LUẬT PHÊ DUYỆT BẢN VẼ được chốt bằng code, không chỉ nằm trong prompt."""
    state = {
        "messages": [AIMessage(content="[Reviewer Agent] PHÊ DUYỆT: hợp lệ", name="ReviewerAgent")],
        "sender": "cad",
        "completed_agents": ["cad"],
    }
    assert agents.supervisor_node(state)["next"] == "FINISH"


def test_handoff_cap_stops_runaway_orchestration():
    state = {
        "messages": [AIMessage(content="[Reviewer Agent] PHÊ DUYỆT: hợp lệ", name="ReviewerAgent")],
        "sender": "qs",
        "completed_agents": ["electrical"] * agents.MAX_AGENT_HANDOFFS,
    }
    assert agents.supervisor_node(state)["next"] == "FINISH"


def test_empty_conversation_finishes():
    assert agents.supervisor_node({"messages": []})["next"] == "FINISH"


def test_supervisor_context_lists_completed_agents_and_recent_messages():
    state = {
        "messages": [
            HumanMessage(content="Thiết kế hệ điện rồi lập dự toán"),
            AIMessage(content="Đã tính xong phụ tải và chọn cáp.", name="ElectricalAgent"),
        ],
        "completed_agents": ["electrical"],
    }
    context = agents._supervisor_context(state)
    assert "electrical" in context.content
    assert "chọn cáp" in context.content


def test_new_user_request_resets_orchestration_history(monkeypatch):
    """Yêu cầu mới phải xóa lịch sử điều phối, nếu không trần handoff sẽ cạn dần và
    các câu hỏi sau bị FINISH ngay lập tức."""
    class _Stub:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            return agents.RouteResponse(next="electrical")

    monkeypatch.setattr(agents, "get_llm", lambda role=None: _Stub())
    state = {"messages": [HumanMessage(content="Tính cáp cho tủ MSB")], "completed_agents": ["qs", "cad"]}
    result = agents.supervisor_node(state)
    assert result["next"] == "electrical"
    assert result["completed_agents"] == [RESET]
    assert result["retry_count"] == 0


def test_append_or_reset_reducer():
    assert append_or_reset(["a"], ["b"]) == ["a", "b"]
    assert append_or_reset(["a", "b"], [RESET]) == []
