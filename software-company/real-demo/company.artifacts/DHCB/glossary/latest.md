# Glossary — DHCB (v0.1, 2026-09-04)

Trạng thái: **SƠ BỘ / KHÔNG ĐỦ**. Đầu vào từ intake có `data` rỗng nên chưa có khái niệm nghiệp vụ nào để định nghĩa. Chỉ ghi những gì xác minh được từ worktree.

| Thuật ngữ | Định nghĩa | Từ đồng nghĩa / cách khách gọi | Nguồn | Tin cậy |
|---|---|---|---|---|
| Đồng Hành Cùng Bạn (DHCB) | Tên tổ chức/sản phẩm gắn với domain donghanhcungban.com. Bản chất hoạt động **chưa xác định**. | donghanhcungban.com, DHCB, `dhcb` (tên package) | `README.md:1-3`, `pyproject.toml:3-4` | trung bình |
| bản demo website | README tự mô tả repo là "bản demo website", tức chưa phải sản phẩm production. | demo, bản thử | `README.md:3` | cao |
| `dhcb` (package) | Python package rỗng, chỉ chứa docstring; là nơi code sẽ được thêm vào. | — | `dhcb/__init__.py:1` | cao |

## Chưa có mục cho (cần intake/clarifier bổ sung goals)
- Người dùng / đối tượng thụ hưởng của DHCB
- Loại nội dung hoặc dịch vụ chính của website
- Có khái niệm "quyên góp", "đăng ký", "tư vấn", "tình nguyện viên"? — **không suy đoán**

## Quy tắc dùng
Mọi tài liệu sau (requirements, ADR, code, UI copy) phải dùng đúng thuật ngữ ở bảng trên. Thêm khái niệm mới → cập nhật file này, tăng version.
