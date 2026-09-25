# 2026-09-25 — tích hợp product excellence vào đúng Claude-Agents

## Mục tiêu và phạm vi

Chủ dự án đính chính repo đích. Bản trước ở X-Agents #113 chưa merge không thuộc Claude-Agents.
Căn cứ base b84dcb76b9085a686dafae97f47c988ac872446a. Tái dùng uv workspace/6 agent, quality_floor
ADR-0043 và execution kernel ADR-0017. Không copy đè AGENTS/CLAUDE hoặc generated sc-*.

Thêm company product quality + native adapter; command product-goal nối thi-hanh; tài liệu sản phẩm/ngành;
core chỉ sửa cleanup lỗi khởi tạo SQLite. H1/H2 không bị mô tả thành H7 hoàn chỉnh.

## Bằng chứng thực thi

- TDD: test module chưa có → import đỏ; adapter chưa có → import đỏ; SQLite init failure → hai test đỏ.
- Core gốc được tái dựng để test nhỏ rồi đối chiếu Git blob e435238e88d592f082ff33e9e3200f039ee49156.
- Snapshot đầy đủ lấy bằng git archive của đúng base qua GitHub Actions **chỉ đọc**, vì container không
  phân giải được github.com. Archive artifact SHA256 7b143b7dfbe93cf377d0521727c4c1249c32f331f6c39ce18fb860df8fb604a7.
- Python local 3.13.5: 116 test mới tổng cộng; hai module mới 398 statements +156 branches, 100%.
- Toàn core: 544 passed; 2676 statements +712 branches, 100%.
- Company: collect 1569; modules mới + quality_floor hiện có: 158 passed, hai module mới 100%.
- Full company local timeout (không có kết luận pass). Test cũ `test_merge_tich_hop_khong_chay_dong_thoi`
  fail với cùng trạng thái blocked trên cả base và nhánh mới; không xóa/skip hoặc nới test để xanh.
- Ruff/mypy chưa cài tại local; dùng cổng CI thực tế trên PR để kiểm toàn workspace. Không coi parse3.11
  là chạy Python3.11. Bằng chứng full CI phải đọc trên đúng head SHA trước khi ready/merge.

## Ranh giới chưa triển khai

Không spawn subagent/reviewer độc lập trong phiên này (không có tool đó). Không có driver browser/restore
mới, không lấy fixture receipt làm proof người dùng, không bật cờ autoapprove hoặc thay gate spec.
Adapter không tự đưa result vào journal; coordinator/authority/lease H3–H7 vẫn phải nối theo lộ trình.

## Người sau không được quên

Chỉ PR trong Claude-Agents mới là bản tích hợp đích. Giữ nguyên sàn chất lượng, journal single-writer
và các nguồn quyền. Đừng dùng token/key do worker cung cấp. Không nhận quality_pass làm quyền deploy.
Cập nhật số PR/CI trong bản ghi này; chưa merge thì bảng B không được ghi xong #n.

## PR đích

PR **#335** — `feat/product-excellence-integration` → `main` trong **Claude-Agents**.
CI cuối và review độc lập chưa có kết luận trong bản ghi này; không tự đánh dấu merged.
Helper source-export/patch-delivery chỉ ở nhánh phụ phục vụ truyền file do container thiếu mạng;
không đưa helper hoặc thay đổi workflow vào cây commit cuối của PR. Không sửa main, không hạ CI.
