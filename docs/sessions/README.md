# Nhật ký phiên

Một file mỗi ngày làm việc: `YYYY-MM-DD.md`. Nhiều phiên trong ngày thì thêm mục trong cùng file. Đây là **bàn
giao ca viết ra** (TRUC-VA-DUNG-KHAN §2), không phải nhật ký tâm sự: người sau đọc 2 phút phải biết đứng ở đâu.

Mẫu:

```markdown
# 2026-MM-DD

## Phiên <giờ bắt đầu> — <một dòng việc chính>
- Xong: <PR #, đã merge/đang chờ CI>
- Dở: <việc, dừng ở đâu, vì sao>
- Đang mở: <PR/gate/ticket cần người theo>
- Bẫy mới: <đã ghi TRAPS.md mục nào; hoặc "không">
- Người sau KHÔNG được quên: <một dòng>
```

Giữ 30 ngày gần nhất; cũ hơn thì gộp vào `CHANGELOG.md` (việc) và `TRAPS.md` (bài học) rồi xoá.
