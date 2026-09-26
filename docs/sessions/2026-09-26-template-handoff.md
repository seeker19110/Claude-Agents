# Phiên tích hợp hai chiều — 2026-09-26

PR #353; companion seeker19110/projects-template#181. Không sửa PR #352.
X-Agents xuất policy/native prepare; template xuất spec/plan; không cấp quyền.

## Kiểm thử cục bộ

73 ca: 52 pytest consumer, 21 unittest producer. Coverage riêng hai module mới
100% dòng và nhánh. CLI trao đổi với native schema thật đã chạy; spec/policy đổi bị từ chối.
Đã tái hiện lỗi Approved trong Draft và CRLF trước sửa. Không gọi model trả phí.
Môi trường không clone được GitHub; nguồn nền đối chiếu Git blob SHA qua connector.
Không claim full workspace cục bộ hoặc production verification.

## CI thật trên GitHub

Lượt CI 36249174816 trên head 7b4e6549b8cad45e5bdea7c028690383b2fd156f:
software-company Ubuntu 3.13 có 1901 passed / 1 failed; lỗi duy nhất là README khai
102 file test thay vì 103. Coverage toàn package: 7957 statements, 2588 branches,
không dòng/nhánh thiếu, 100%. Console Ubuntu 3.13 có 484 passed / 1 failed vì
README gốc khai 1850 thay vì 1902 test software-company. Ruff/mypy, golden/replay,
audit và unit của core/gateway/keeper đã qua. Commit tài liệu kế tiếp sửa đúng
hai số liệu theo CI, không sửa test hoặc hạ sàn. Cần đọc CI của head mới để kết luận.

Template: PR policy, Secret scan, Dependency review và CodeQL đã qua trên 910ff752;
CI tổng tại lần kiểm tra này chưa có kết luận cuối. Đây không phải claim xanh toàn repo.

Chặn merge: CI trên head cuối + review độc lập. Giữ draft, không auto-merge.
Bản đối chiếu và trần: ../reports/2026-09-26-bidirectional-delivery-handoff.md.
