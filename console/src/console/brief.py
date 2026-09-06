"""C8 — hồ sơ `gate_brief` ngay cạnh nút duyệt, không phải trong một cửa sổ terminal khác.

Nửa "Người tự kiểm thêm" của checklist gate là nửa mà người ký phải tự đi tìm bằng chứng. `company.gate_brief` đã
dựng sẵn hồ sơ đó, nhưng chỉ chạy được bằng CLI — nghĩa là người trực đang cầm chuột trên nút *Duyệt* phải mở một
terminal, nhớ đường dẫn DB, rồi đọc file. Đêm 05/09 việc đó đơn giản là không xảy ra: người ký trên thứ mình không
đọc.

Module này gọi thẳng `company.gate_brief.build` / `render_md` (chỉ đọc: `mode=ro`, `FakeClient`, không publish,
không gọi model) và trả Markdown cho trang. Không chép lại một dòng logic nào của công ty — hồ sơ trên trang và hồ
sơ do `/gate-brief` sinh ra phải là cùng một văn bản, nếu không thì người ký và trợ lý kiểm duyệt đọc hai thứ khác
nhau.

Chỉ có software-company: xưởng video chưa có `gate_brief` (studio C2 chưa làm), và nói "chưa có" đúng hơn là dựng
một hồ sơ rỗng nhìn như đã kiểm.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

COMPANY = "software-company"


class BriefUnavailable(Exception):
    """Không dựng được hồ sơ — thông điệp tiếng Việt, hiện thẳng trong ngăn kéo thay cho hồ sơ."""


def gate_brief(company_db: Path | None, subject_id: str, *, xuong: str = COMPANY, closed: bool = False) -> dict[str, Any]:
    """`{"subject_id", "kind", "md"}` — Markdown y hệt `python -m company.gate_brief <subject>` in ra."""
    if xuong != COMPANY:
        raise BriefUnavailable(f"chưa có hồ sơ bằng chứng cho xưởng {xuong} — mới chỉ software-company có `gate_brief`")
    if not subject_id.strip():
        raise BriefUnavailable("thiếu subject_id")
    if company_db is None or not Path(company_db).exists():
        raise BriefUnavailable(f"chưa có file DB của {COMPANY}: {company_db or '(chưa cấu hình)'}")
    from company import gate_brief as gb  # nhập trễ: đây là đường đắt (replay cả log), chỉ trả giá khi có người mở

    try:
        orch = gb.load_state(Path(company_db))
        data = gb.build(orch, subject_id, closed=closed)
        md = gb.render_md(data)
    except gb.NotPending as e:
        raise BriefUnavailable(str(e)) from e
    except gb.BriefError as e:
        raise BriefUnavailable(f"không dựng được hồ sơ: {e}") from e
    except Exception as e:  # log hỏng, checklist đổi hình dạng… — hiện lý do, đừng để nút im lặng
        raise BriefUnavailable(f"lỗi khi dựng hồ sơ: {type(e).__name__}: {str(e)[:200]}") from e
    return {"subject_id": subject_id, "kind": data.get("kind", ""), "md": md}
