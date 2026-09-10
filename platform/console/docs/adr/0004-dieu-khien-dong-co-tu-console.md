# ADR-0004 — Console bật/tắt được động cơ của từng xưởng

Ngày: 2026-09-09 · Trạng thái: chấp nhận · Thay thế: không · Liên quan: ADR-0001 (console hợp nhất), ADR-0003 (ô rỗng là ô xám)

## Bối cảnh

Trước quyết định này console làm được ba việc: **nhìn** (đọc bus chỉ đọc), **giao việc** (`--allow-submit`) và
**ký gate** (`--allow-decide`). Vòng lặp xử lý — `orchestrator run --watch` — vẫn phải do người tự bật ở một
terminal khác.

Chỗ hụt đó không phải bất tiện, nó là một **chế độ hỏng im lặng**: giao việc trên trang khi chưa bật orchestrator
thì event nằm trên bus, trang không báo lỗi (event publish thành công thật), gate không bao giờ mở, và người trực
kết luận sai rằng "công ty đang nghĩ". `CLAUDE.md` của package phải dặn bằng chữ — "bật console thì bật luôn
`run --watch`" — đúng dấu hiệu của một thứ lẽ ra phải do máy đảm bảo chứ không phải do người nhớ.

## Quyết định

Console bật/tắt được động cơ của cả ba xưởng, sau một cờ **riêng** `--allow-engine`, qua `POST /api/engine`
(`console/src/console/engine.py`). Trạng thái ba động cơ đi kèm trong `/api/state` và `/api/stream`.

Bốn ràng buộc là một phần của quyết định, không phải chi tiết cài đặt:

1. **Quyền riêng, không gộp.** `--allow-engine` tách khỏi `--allow-decide` / `--allow-submit` / `--allow-config`.
   Đây là quyền nặng nhất trong bốn: nó tạo tiến trình con **gọi model** (tiêu hạn mức, tiêu tiền) và **ghi**
   vào repo khách qua worktree. Người được ký gate không đương nhiên là người được đốt ngân sách.
2. **Không tham số nào của người đi vào dòng lệnh.** `argv` dựng từ bảng `SPECS` chốt cứng trong mã nguồn; thứ
   duy nhất client đặt được là `interval` (float, kẹp `[5, 3600]`). Không `shell=True`, không đường dẫn từ body.
   Console đã là bề mặt HTTP duy nhất chạm được vào gate; biến nó thành bề mặt chạy lệnh tuỳ ý thì một lỗ XSS
   nhỏ ở trang thành thực thi mã.
3. **Con chết cùng cha.** `stop_all()` chạy ở `server_close()` và `atexit`. Một orchestrator mồ côi vẫn ghi bus
   sau khi người trực đã tắt console là đúng thứ tệ nhất: công ty chạy mà không ai nhìn.
4. **Trạng thái đo được, không khai báo.** `status()` gọi `poll()` mỗi lần hỏi. Động cơ chết vì thiếu `llm.yaml`
   phải hiện `exited` + mã thoát + đuôi log, không hiện `running` vì ta *đã từng* bấm Bật (ADR-0003).

## Phương án đã cân nhắc

- **Giữ nguyên, chỉ thêm cảnh báo trên trang** ("orchestrator không chạy"). Rẻ, nhưng chỉ đổi một hỏng im lặng
  thành một hỏng có nhãn: người trực vẫn phải rời trang, mở terminal, nhớ đúng thư mục (`software-company/`, vì
  gốc repo có `company.sqlite` rỗng). Cảnh báo đó vẫn nên có — nó là hệ quả phụ của ô Động cơ, không phải thay thế.
- **Console tự bật orchestrator khi khởi động.** Bỏ hẳn một bước, nhưng biến `python -m console` — lệnh người ta
  gõ để *nhìn* — thành lệnh tiêu tiền. Trái với "chỉ đọc là mặc định" (ADR-0001).
- **Nhúng vòng lặp vào chính tiến trình console** (thread thay vì subprocess). Bỏ được lớp quản tiến trình, nhưng
  một exception trong vòng agent sẽ giết luôn mặt kính trực ban, và console phải nhập cả `Orchestrator` của ba
  công ty. Tiến trình riêng giữ đúng ranh giới cũ: console không *là* công ty, nó *gọi* công ty bằng đúng CLI mà
  người vẫn gõ — dòng lệnh đó in nguyên văn vào đầu file log để đối chiếu.

## Hệ quả

- Người trực làm trọn vòng trên một trang: bật động cơ → giao việc → ký gate → xem kết quả → tắt động cơ.
- Console giờ có tiến trình con: `console/.engine/*.log` (đã gitignore) và một đường dọn khi thoát.
- Động cơ do console bật **chết khi tắt console**. Muốn chạy dài ngày qua nhiều phiên console thì vẫn bật ở
  terminal như cũ — ô Động cơ chỉ thấy tiến trình do chính nó tạo, và nói rõ điều đó.
