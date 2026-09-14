---
description: Viết một ADR đúng khuôn của repo — đo hiện trạng bằng số trước, nêu phương án đã loại và vì sao, đánh số tiếp theo, link vào PR
---

Viết một **ADR** (quyết định kiến trúc) cho `$ARGUMENTS`.

> `AGENTS.md` luật bắt buộc 2: **đổi kiến trúc thì ADR đi trước**, link trong PR. Sửa lỗi nhỏ, chỉnh prompt,
> sửa tài liệu thì không cần — đừng viết ADR cho việc không phải quyết định.

## Bước 1 — Chọn chỗ và số

ADR cấp repo → `docs/adr/`. ADR của một công ty/package → `<gói>/docs/adr/` (ví dụ
`companies/software-company/docs/adr/`). Số tiếp theo = số lớn nhất đang có + 1, bốn chữ số, tên file
`NNNN-<mô-tả-kebab-tiếng-việt-không-dấu>.md`. Đọc thư mục thật để lấy số — **không đoán**.

## Bước 2 — Đo hiện trạng bằng SỐ trước khi viết một chữ nào

ADR của repo này mở đầu bằng đo, không bằng ý kiến (xem `docs/adr/0001-loi-chung-xagents-core.md`: bảng dòng
code trùng nguyên văn giữa hai bản fork). Chạy lệnh thật — `grep -c`, `wc -l`, `git log`, một phép đo thời gian
— và **dán số vào ADR**. Không có số thì đó là bài luận, không phải quyết định.

## Bước 3 — Khuôn

```markdown
# ADR-NNNN: <quyết định, viết ở thể khẳng định>

Ngày: <YYYY-MM-DD> · Trạng thái: được chấp nhận · Epic: <nếu có>

## Bối cảnh
<hiện trạng ĐO ĐƯỢC: bảng số, đường dẫn file:dòng. Vì sao hiện trạng này không giữ được.>

## Quyết định
<làm gì, thể khẳng định. Cái gì đổi, cái gì cố ý giữ nguyên.>

## Phương án đã loại
<mỗi phương án một đoạn: nó là gì, ưu điểm thật của nó, vì sao vẫn loại. Không có mục này thì
ADR chỉ là biện hộ cho việc đã quyết rồi.>

## Hệ quả
<phải sửa gì theo · cái gì trở nên khó hơn · di cư ra sao · rủi ro và cách nhận biết nếu quyết định này sai>
```

## Bước 4 — Nối vào phần còn lại

Link ADR trong mô tả PR. Đổi kiến trúc thì `ARCHITECTURE.md`/`CODEMAP.md` của package phải cập nhật **trong
cùng PR** (luật bắt buộc 10), cùng dòng `CHANGELOG.md`. ADR thay thế một ADR cũ → sửa trạng thái ADR cũ thành
"bị thay bởi ADR-NNNN", không xoá nó.

Bắt đầu Bước 1: liệt kê thư mục ADR liên quan để lấy số tiếp theo.
