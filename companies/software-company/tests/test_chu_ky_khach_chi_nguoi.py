"""`acceptance-results` là chữ ký của khách — không agent nào được xuất ra nó (sc-security 2026-09-23, lỗ để ngỏ ở
ADR-0043: "`ops` là producer của `acceptance-results`, chưa đo agent có tự ghi được không").

Đo: `runner.publish` chỉ phát lên `topic_out` của ROUTE; không route nào (kể cả `THREAT_ROUTE`) có
`topic_out="acceptance-results"`; đường thật của khách là `orchestrator publish --actor human:<tên>` (CLI từ chối
actor không phải người). Quyền `ops` trong bảng ACL chỉ phản chiếu `writes` của front matter `ops.md` (và hai ca
eval pha `account`) — gỡ nó là đổi hợp đồng agent, cần `make eval-record` bằng model thật (CONTRIBUTING §3).

Vì vậy thứ phải CANH là bất biến dưới đây: sau ADR-0043 một chữ ký `accepted` đóng ticket, nên ngày ai đó thêm
route cho agent xuất `acceptance-results` là ngày agent ký thay khách — test này đỏ đúng ngày đó."""
from pathlib import Path

from company.orch.routes import ROUTES, THREAT_ROUTE


def test_khong_route_nao_cho_agent_xuat_chu_ky_khach():
    assert [(r.topic_in, r.agent) for r in (*ROUTES, THREAT_ROUTE) if r.topic_out == "acceptance-results"] == []


def test_cli_publish_chi_nhan_actor_nguoi(tmp_path: Path):
    from company.orch.cli import main
    f = tmp_path / "a.json"
    f.write_text('{"release_id": "REL-1", "project_id": "P", "verdict": "accepted", "signed_by": "khach"}',
                 encoding="utf-8")
    db = tmp_path / "c.sqlite"
    assert main(["--db", str(db), "publish", "acceptance-results", str(f), "--actor", "ops"]) == 2
    assert main(["--db", str(db), "publish", "acceptance-results", str(f), "--actor", "human:khach"]) == 0
