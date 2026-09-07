import pytest

from company import registry as R
from company.delivery import DeliveryLead
from company.events import NAMESPACE_OWNERS
from company.registry import SKILLS_DIR, _split, load_agents, load_skill
from company.roles import SOURCE

EXPECTED = {
    # research (6) — ADR-0006 gộp domain/ux-designer/codebase/tech-scout thành researcher
    "intake", "researcher", "synthesizer", "risk", "clarifier", "spec-writer",
    # delivery (1)
    "delivery-lead",
    # engineering (1) — ADR-0037 PR-5d: backend + frontend + mobile + database + platform + data gộp thành
    # `builder`, sáu tên cũ thành PHA chọn theo `stack` của ticket
    "builder",
    # quality (2) — ADR-0037 PR-5c: test-author + reviewer + qa-debugger gộp thành `qa` (pha `author`/`review`)
    "qa", "security",
    # operations (1) — ADR-0037 PR-5b: release-engineer + support-docs + account-manager gộp thành `ops`
    "ops",
    # supervision (1)
    "supervisor",
}

def test_all_12_agents_load():
    agents = load_agents()
    assert set(agents) == EXPECTED
    assert len(agents) == 12

def test_prompts_have_skills_and_dod():
    for a in load_agents().values():
        assert "Definition of done" in a.prompt
        # ADR-0037: agent theo pha (vd. `ops`) có thể không có skill nào ở CẤP AGENT (skills: []) — mọi skill
        # sống trong `phases.*`, vẫn nạp đầy đủ ở đúng lượt (xem `AgentSpec.system_prompt`). Không rỗng CẢ HAI
        # thì mới là agent thiếu skill thật.
        assert a.skill_text or a.phases, a.id
        assert a.budget_tokens_per_task > 0

def test_prompt_versions_at_least_1():
    """ADR-0004: prompt là code, mỗi agent có version ≥ 1."""
    for a in load_agents().values():
        assert isinstance(a.version, int) and a.version >= 1, a.id

def test_namespace_write_matches_events_owner():
    """Front matter `context_namespace_write` phải khớp NAMESPACE_OWNERS trong events.py."""
    for a in load_agents().values():
        for ns in a.namespaces_write:
            assert a.id in NAMESPACE_OWNERS[ns], (a.id, ns)

def test_every_namespace_owner_is_a_real_agent():
    agents = set(load_agents())
    for ns, owners in NAMESPACE_OWNERS.items():
        assert owners <= agents, (ns, owners - agents)

def test_split_bao_loi_khi_thieu_front_matter():
    with pytest.raises(ValueError, match="thiếu front matter"):
        _split("# Không có front matter\nchỉ có nội dung.\n")


def test_load_skill_core_only_bao_loi_khi_khong_co_muc_loi(tmp_path, monkeypatch):
    """`core_only=True` chỉ giữ H1 + `## Quy trình`/`## Checklist` (ADR-0008) — thiếu cả hai thì báo rõ."""
    (tmp_path / "khong-loi.md").write_text(
        "---\nname: khong-loi\n---\n# Skill: khong-loi\n\n## Tiêu chuẩn\nchi tiết không phải quy trình.\n",
        encoding="utf-8")
    monkeypatch.setattr(R, "SKILLS_DIR", tmp_path)
    with pytest.raises(ValueError, match="không tìm thấy mục lõi"):
        load_skill("khong-loi", core_only=True)


def test_load_agents_bao_loi_khi_skill_vua_day_du_vua_rut_gon(tmp_path, monkeypatch):
    """ADR-0008: một skill không được vừa nằm trong `skills` (đầy đủ) vừa trong `skills_core` (rút gọn)."""
    skills_dir = tmp_path / "skills"; agents_dir = tmp_path / "agents"
    skills_dir.mkdir(); agents_dir.mkdir()
    (skills_dir / "dung-chung.md").write_text(
        "---\nname: dung-chung\n---\n# Skill: dung-chung\n\n## Quy trình\nlàm x.\n\n## Checklist\n- [ ] x\n",
        encoding="utf-8")
    (agents_dir / "trung.md").write_text(
        "---\nid: trung\nblock: engineering\nmodel_tier: standard\nreads: []\nwrites: []\n"
        "context_namespace_write: null\nskills: [dung-chung]\nskills_core: [dung-chung]\n"
        "budget_tokens_per_task: 1000\nmax_retries: 1\ntimeout_minutes: 10\n---\n# trung\nDoD.\n",
        encoding="utf-8")
    monkeypatch.setattr(R, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(R, "AGENTS_DIR", agents_dir)
    with pytest.raises(ValueError, match="skill vừa đầy đủ vừa rút gọn"):
        load_agents(check_owners=False)


def test_skill_front_matter_name_matches_filename():
    for p in SKILLS_DIR.glob("*.md"):
        fm, _ = _split(p.read_text(encoding="utf-8"))
        assert fm["name"] == p.stem, p.name

def test_no_orphan_skill():
    used = {s for a in load_agents().values() for s in a.all_skills}
    on_disk = {p.stem for p in SKILLS_DIR.glob("*.md")}
    assert on_disk == used, {"unused": on_disk - used, "missing": used - on_disk}


def test_every_skill_has_an_owning_agent():
    """ADR-0008: skill chỉ xuất hiện ở `skills_core` thì phần Quy tắc/Ví dụ không tới tay model nào."""
    owned = {s for a in load_agents().values() for s in a.owned_skills}  # ADR-0037: kể cả skill khai trong một pha
    on_disk = {p.stem for p in SKILLS_DIR.glob("*.md")}
    assert on_disk <= owned, sorted(on_disk - owned)


def test_load_agents_rejects_ownerless_skill(tmp_path, monkeypatch):
    import company.registry as reg

    monkeypatch.setattr(reg, "SKILLS_DIR", tmp_path)
    for p in SKILLS_DIR.glob("*.md"):
        (tmp_path / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "khong-ai-so-huu.md").write_text(
        "---\nname: khong-ai-so-huu\nversion: 1\n---\n# Skill\n\n## Quy trình\nx\n\n## Checklist\n- x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="chủ quản"):
        reg.load_agents()


def test_context_namespace_read_names_real_namespaces():
    """ADR-0020: mọi namespace trong context_namespace_read phải tồn tại; review/QA/ops có trần prompt riêng thấp hơn."""
    from company.events import NAMESPACE_OWNERS
    agents = load_agents()
    for spec in agents.values():
        assert spec.context_namespace_read is not None, f"{spec.id}: thiếu context_namespace_read"
        assert set(spec.context_namespace_read) <= set(NAMESPACE_OWNERS), spec.id
    for aid in ("qa", "security", "ops", "supervisor"):
        assert agents[aid].max_input_chars and agents[aid].max_input_chars <= 70_000, aid


def test_review_tiers_per_adr0021():
    agents = load_agents()
    assert agents["qa"].model_tier == "standard", "ADR-0021: chấm code/test dùng tier standard"
    assert agents["security"].model_tier == "strong", "separation of duties: security giữ tier mạnh"
    # ADR-0037: `qa` chấm MỌI PR (route pha `review` không còn guard risk_tags) nên nó là review NỀN, không
    # phải review "thêm" của ticket rủi ro — chỉ `security` mới là.
    assert DeliveryLead.RISK_REVIEWS == {SOURCE.SECURITY} and DeliveryLead.BASE_REVIEWS == {SOURCE.REVIEWER}


# ---------- ADR-0037: skill theo pha ----------

def _skill_md(name: str) -> str:
    """Skill có đủ mục lõi + một mục chuyên sâu, để phân biệt bản đầy đủ với bản rút gọn."""
    return (f"---\nname: {name}\n---\n# Skill: {name}\n\n## Quy trình\nbước của {name}.\n\n"
            f"## Checklist\n- [ ] {name}\n\n## Quy tắc\nCHUYEN-SAU-{name}\n")


def _cay_pha(tmp_path, monkeypatch, front_matter: str, skills: tuple[str, ...]):
    """Cây agents/skills giả để đo `phases` mà không đụng agent thật của repo."""
    skills_dir = tmp_path / "skills"; agents_dir = tmp_path / "agents"
    skills_dir.mkdir(); agents_dir.mkdir()
    for s in skills:
        (skills_dir / f"{s}.md").write_text(_skill_md(s), encoding="utf-8")
    (agents_dir / "a.md").write_text(
        "---\nid: a\nblock: engineering\nmodel_tier: standard\nreads: []\nwrites: []\n"
        "context_namespace_write: null\nbudget_tokens_per_task: 1000\nmax_retries: 1\ntimeout_minutes: 10\n"
        + front_matter + "---\n# a\nDefinition of done: xong.\n", encoding="utf-8")
    monkeypatch.setattr(R, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(R, "AGENTS_DIR", agents_dir)
    return skills_dir, agents_dir


def test_skill_cua_pha_chi_vao_prompt_cua_dung_pha(tmp_path, monkeypatch):
    """ADR-0037: `skills` cấp agent nạp ở mọi lượt; `phases.<tên>.skills` chỉ nạp khi lượt khai đúng pha đó —
    đó là toàn bộ lý do gộp 21 agent thành 5 mà prompt không loãng."""
    _cay_pha(tmp_path, monkeypatch,
             "skills: [chung]\nphases:\n  intake: {skills: [rieng-intake]}\n  spec: {skills: [rieng-spec]}\n",
             ("chung", "rieng-intake", "rieng-spec"))
    a = load_agents(check_owners=False)["a"]
    assert set(a.phases) == {"intake", "spec"}
    chung = a.system_prompt()
    assert "CHUYEN-SAU-chung" in chung
    assert "CHUYEN-SAU-rieng-intake" not in chung and "CHUYEN-SAU-rieng-spec" not in chung
    intake = a.system_prompt("intake")
    assert "# Skills của pha intake" in intake and "CHUYEN-SAU-rieng-intake" in intake
    assert "CHUYEN-SAU-rieng-spec" not in intake, "pha này không được nạp skill của pha kia"
    assert "CHUYEN-SAU-chung" in intake, "skill cấp agent vẫn nạp ở mọi pha"


def test_pha_thang_ban_rut_gon_cung_ten_o_cap_agent(tmp_path, monkeypatch):
    """Trùng giữa hai CẤP là hợp lệ và pha thắng: skill được pha nạp đầy đủ không được gửi kèm bản rút gọn nữa
    (vd. `observability` của builder) — gửi cả hai là trả tiền hai lần cho cùng một skill."""
    _cay_pha(tmp_path, monkeypatch,
             "skills: []\nskills_core: [do-luong]\nphases:\n  platform: {skills: [do-luong]}\n",
             ("do-luong",))
    a = load_agents(check_owners=False)["a"]
    chung = a.system_prompt()
    assert "CHUYEN-SAU-do-luong" not in chung and "bước của do-luong" in chung, "không pha: chỉ bản rút gọn"
    platform = a.system_prompt("platform")
    assert platform.count("bước của do-luong") == 1, "không được nạp cả bản đầy đủ lẫn bản rút gọn"
    assert "CHUYEN-SAU-do-luong" in platform


def test_system_prompt_bao_loi_khi_pha_khong_co_trong_front_matter(tmp_path, monkeypatch):
    """Pha lạ phải nổ, không được im lặng trả prompt chung: lượt chạy với bộ skill của vai khác mà không ai thấy."""
    _cay_pha(tmp_path, monkeypatch, "skills: [chung]\nphases:\n  intake: {skills: []}\n", ("chung",))
    a = load_agents(check_owners=False)["a"]
    with pytest.raises(KeyError, match="không có pha"):
        a.system_prompt("khong-co")


def test_pha_khong_duoc_trung_skill_trong_cung_mot_cap(tmp_path, monkeypatch):
    _cay_pha(tmp_path, monkeypatch,
             "skills: []\nphases:\n  intake: {skills: [chung], skills_core: [chung]}\n", ("chung",))
    with pytest.raises(ValueError, match=r"a\[intake\]: skill vừa đầy đủ vừa rút gọn"):
        load_agents(check_owners=False)


def test_pha_khong_duoc_khai_lai_skill_da_day_du_o_cap_agent(tmp_path, monkeypatch):
    """Đầy đủ ở cả hai cấp là dư thừa im lặng — cùng một skill vào prompt hai lần ở mọi lượt của pha."""
    _cay_pha(tmp_path, monkeypatch, "skills: [chung]\nphases:\n  intake: {skills: [chung]}\n", ("chung",))
    with pytest.raises(ValueError, match="đã nạp đầy đủ ở cấp agent"):
        load_agents(check_owners=False)


def test_skill_chi_nam_o_mot_pha_van_co_chu_quan(tmp_path, monkeypatch):
    """ADR-0008 tính trên HỢP của cấp agent và mọi pha (ADR-0037): skill chỉ khai ở một pha vẫn được nạp đầy đủ
    ở lượt của pha đó, nên nó có chủ quản. Tính chủ quản chỉ trên `skills` cấp agent thì `load_agents()` báo mồ côi."""
    _cay_pha(tmp_path, monkeypatch, "skills: []\nphases:\n  spec: {skills: [chi-o-pha]}\n", ("chi-o-pha",))
    a = load_agents()["a"]  # check_owners=True: không được ném
    assert a.owned_skills == ["chi-o-pha"] and a.all_skills == ["chi-o-pha"]
    assert a.skills == [], "skill không nằm ở cấp agent"


def test_skill_chi_nam_o_skills_core_cua_pha_van_la_mo_coi(tmp_path, monkeypatch):
    """Chiều ngược lại: pha nạp RÚT GỌN thì phần Quy tắc vẫn không tới tay model nào → vẫn là mồ côi."""
    _cay_pha(tmp_path, monkeypatch, "skills: []\nphases:\n  spec: {skills_core: [chi-rut-gon]}\n", ("chi-rut-gon",))
    with pytest.raises(ValueError, match="chủ quản"):
        load_agents()
