"""Đo token THẬT theo vai trò, thay cho ước lượng bịa len(text)/4 ở UI cũ."""
from langchain_core.messages import AIMessage

from src.usage import PRICE_PER_MTOK, UsageTracker, record_usage, reset_tracker


def _ai_message(model, input_tokens, output_tokens):
    msg = AIMessage(content="xong")
    msg.response_metadata = {"model_name": model}
    msg.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    return msg


def test_tokens_accumulate_per_role():
    tracker = reset_tracker()
    record_usage("Mechanical", _ai_message("gpt-4o-mini", 1000, 200))
    record_usage("Mechanical", _ai_message("gpt-4o-mini", 500, 100))
    record_usage("QS", _ai_message("gpt-4o-mini", 300, 50))

    assert tracker.by_role["Mechanical"].input_tokens == 1500
    assert tracker.by_role["Mechanical"].calls == 2
    assert tracker.by_role["QS"].total_tokens == 350
    assert tracker.total_tokens == 2150


def test_cost_uses_separate_input_and_output_rates():
    tracker = reset_tracker()
    record_usage("Reviewer", _ai_message("gpt-4o-mini", 1_000_000, 1_000_000))
    in_rate, out_rate = PRICE_PER_MTOK["gpt-4o-mini"]
    assert tracker.by_role["Reviewer"].cost_usd == in_rate + out_rate


def test_unknown_model_counts_tokens_but_reports_no_price():
    """Thà không báo giá còn hơn báo một con số sai cho model chưa có bảng giá."""
    tracker = reset_tracker()
    record_usage("CAD", _ai_message("mo-hinh-la-hoac-tu-host", 1000, 500))
    assert tracker.by_role["CAD"].total_tokens == 1500
    assert tracker.by_role["CAD"].cost_usd is None
    assert tracker.total_cost_usd is None


def test_roles_can_mix_priced_and_unpriced_models():
    tracker = reset_tracker()
    record_usage("QS", _ai_message("gpt-4o-mini", 1_000_000, 0))
    record_usage("CAD", _ai_message("llama3.1:8b-tu-host", 1_000_000, 0))
    assert tracker.total_cost_usd == PRICE_PER_MTOK["gpt-4o-mini"][0]
    assert tracker.total_tokens == 2_000_000


def test_message_without_usage_metadata_is_ignored_silently():
    """Backend local (Ollama) có thể không báo usage — thiếu số liệu không được làm
    hỏng luồng tư vấn."""
    tracker = reset_tracker()
    record_usage("BIM", AIMessage(content="không có usage_metadata"))
    assert tracker.by_role == {}
    assert tracker.total_tokens == 0


def test_reset_starts_a_fresh_count():
    tracker = reset_tracker()
    record_usage("QS", _ai_message("gpt-4o-mini", 100, 100))
    assert tracker.total_tokens == 200
    fresh = reset_tracker()
    assert fresh.total_tokens == 0


def test_tracker_add_handles_missing_values():
    tracker = UsageTracker()
    tracker.add("QS", "", None, None)
    assert tracker.by_role["QS"].total_tokens == 0
