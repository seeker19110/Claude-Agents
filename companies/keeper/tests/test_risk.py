"""BT4 — `risk.py`: một ca cho MỖI HÀNG của bảng, cộng ca chiều ngược cho hai hàng `high`.

Ca chiều ngược ở đây là chiều ngược THẬT: nó bỏ đúng hàng đang xét khỏi bảng rồi assert tier ĐỔI (assert cả
hai giá trị), chứ không assert một hằng đúng.
"""
import pytest

from keeper.events import Signal
from keeper.risk import DEFAULT_TIER, RISK_RULES, risk_tier, rules_without


def _names(tier: str) -> list[str]:
    return [r.name for r in RISK_RULES if r.tier == tier]


def test_bang_khong_co_hang_trung_ten():
    names = [r.name for r in RISK_RULES]
    assert len(names) == len(set(names))


@pytest.mark.parametrize(
    ("name", "signal"),
    [
        ("semver-major", Signal(subject="pydantic", kind="dependency", detail="Bump pydantic from 1.9.0 to 2.0.0",
                                semver_jump="major")),
        ("touches-core", Signal(subject="xagents-core/src/xagents_core/supervisor.py", kind="drift",
                                detail="lệch lõi")),
        ("touches-agents-or-skills", Signal(subject="sc-builder.md", kind="drift", detail="lệch prompt",
                                            evidence="agents/engineering/builder.md")),
        ("touches-ci-config", Signal(subject=".github/workflows/ci.yml", kind="drift", detail="workflow đổi")),
        ("touches-coverage-config", Signal(subject="keeper/pyproject.toml", kind="drift",
                                           detail="fail_under bị hạ xuống 99")),
        ("security-high", Signal(subject="requests", kind="security", detail="RCE", severity="high")),
    ],
)
def test_moi_hang_high(name, signal):
    assert name in _names("high")
    assert risk_tier(signal) == "high"


@pytest.mark.parametrize(
    ("name", "signal"),
    [
        ("dev-dependency-patch-minor", Signal(subject="ruff", kind="dependency",
                                              detail="Bump ruff from 0.5.0 to 0.5.1", semver_jump="patch",
                                              is_dev=True)),
        ("docs-only-drift", Signal(subject="pr-200", kind="drift", detail="thiếu dòng CHANGELOG",
                                   evidence="(#200)")),
    ],
)
def test_moi_hang_low(name, signal):
    assert name in _names("low")
    assert risk_tier(signal) == "low"


def test_khong_hang_nao_khop_thi_medium():
    s = Signal(subject="README.txt", kind="health", detail="CI chậm dần")
    assert risk_tier(s) == DEFAULT_TIER == "medium"


def test_dev_dependency_minor_cung_low():
    s = Signal(subject="mypy", kind="dependency", detail="Bump mypy from 2.3.1 to 2.4.0",
               semver_jump="minor", is_dev=True)
    assert risk_tier(s) == "low"


def test_dev_dependency_semver_jump_None_khong_roi_vao_low():
    """`semver_jump=None` (pre-release: ba số không đổi, đo ở BT3 `scout.semver_jump`) KHÔNG được coi là
    patch/minor — không phân loại thì phải là `medium`, không phải `low`."""
    s = Signal(subject="pydantic", kind="dependency", detail="Bump pydantic from 2.0.0 to 2.0.0rc1",
               semver_jump=None, is_dev=True)
    assert s.semver_jump is None
    assert risk_tier(s) == "medium"


def test_dependency_khong_phai_dev_thi_khong_low():
    s = Signal(subject="pydantic", kind="dependency", detail="Bump pydantic from 2.0.0 to 2.0.1",
               semver_jump="patch", is_dev=False)
    assert risk_tier(s) == "medium"


def test_security_medium_khong_high():
    s = Signal(subject="requests", kind="security", detail="thấp", severity="medium")
    assert risk_tier(s) == "medium"


def test_security_critical_van_high():
    s = Signal(subject="requests", kind="security", detail="rất nặng", severity="critical")
    assert risk_tier(s) == "high"


def test_pyproject_khong_dong_toi_coverage_thi_khong_high():
    s = Signal(subject="keeper/pyproject.toml", kind="drift", detail="đổi mô tả package")
    assert risk_tier(s) == "medium"


# --- hai ca CHIỀU NGƯỢC: bỏ hàng khỏi bảng, tier phải TỤT, assert cả hai giá trị ---

def test_chieu_nguoc_bo_hang_touches_core():
    s = Signal(subject="docs/adr/0001.md", kind="drift", detail="lệch tài liệu lõi",
               evidence="xagents-core/docs/adr/0001.md")
    assert risk_tier(s) == "high"
    assert risk_tier(s, rules=rules_without("touches-core")) == "low"


def test_chieu_nguoc_bo_hang_semver_major():
    s = Signal(subject="pydantic", kind="dependency", detail="Bump pydantic from 1.9.0 to 2.0.0",
               semver_jump="major", is_dev=True)
    assert risk_tier(s) == "high"
    assert risk_tier(s, rules=rules_without("semver-major")) == "medium"


def test_rules_without_ten_khong_co_thi_no():
    with pytest.raises(KeyError):
        rules_without("khong-ton-tai")
