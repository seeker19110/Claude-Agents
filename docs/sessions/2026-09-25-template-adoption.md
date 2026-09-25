# 2026-09-25 — tiếp thu projects-template vào Claude-Agents

Repo nguồn được xác minh bằng redirect + repository ID, không nhầm với repo đích. Phân tích chín file
nguồn và đối chiếu code/test đang chạy trước lựa chọn. Bản đối chiếu:
`docs/reports/2026-09-25-projects-template-adoption.md` từ gốc repo. ADR company 0045 viết trước code.

## Thay đổi

DeliveryContract/DeliveryReport nối vào Profile→compile→assess→commit_quality_result hiện có. Ready kiểm
cấu trúc (không cấp authority); Done khác Complete; cổng PASS không được no-op, N/A phải khai trước.
Pin chuẩn nguồn có full SHA và năm blob; giữ hash/signature cũ khi opt-out. Design precedence và repair
root-cause layer ghi trong chính command/charter, không thêm coordinator hoặc sổ trạng thái cạnh tranh.

## Xác minh cục bộ

TDD import đỏ trước module mới. Nhóm delivery + quality + floor + role: 240 passed; ba module liên quan
596 statements / 236 branches, 100% dòng và nhánh. CLI profile ví dụ được compile, graph giữ work scope
và journal replay/ACK được test. Đây là fixture tổng hợp, không browser/product/approval evidence thật.
Hash profile v2 mẫu tính bằng mã parent 74bd6de1: fb5dd9731ff1d74353d8f602e1e858c8c6749eac171b767f94d539f11d99332b.

Gate chuẩn `UV_OFFLINE=1 bash scripts/dev-task.sh gate company` dừng trước lint vì cache thiếu librt0.15.0;
không tuyên bố full lint/toolchain local đạt. CI GitHub trên head mới là kiểm chứng riêng phải đọc lại.
Không sửa fail_under/skip caps/CI workflow, không gọi model trả phí. Không có công cụ spawn independent
subagent trong phiên này, không ghi review độc lập giả. Không merge main hoặc thay runtime máy chủ dự án.

## Người tiếp quản

Cập nhật trong cùng PR335; không lấy CI của parent làm dấu xanh head mới. Giữ source pin/registry/keys
ngoài quyền worker. Không lấy trạng thái metadata Approved làm chữ ký thật. H3–H7 và driver thực vẫn là
phần tích hợp riêng, không báo đã triển khai chỉ vì contract compile thành công.

Repo/command guards: 111 passed. Company collect: 1641 ca / 93 file, không gọi collect là đã chạy toàn suite.
Cập nhật cùng bảng B/Q7 của productexcellence; không mở sổ tiến độ hoặc PR cạnh tranh.
