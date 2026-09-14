# ADR-0016: cấu hình model ở tầng cấp máy, `llm.yaml` của package chỉ giữ phần khác nhau

Ngày: 2026-09-09 (viết) · 2026-09-14 (đánh số lại và đo lại khi port) · Trạng thái: được chấp nhận · Lớp: 4
(cấu hình vận hành) · Chạm: `xagents-core` + 2 package có agent

> **Ghi chú port (2026-09-14).** ADR này viết ngày 2026-09-09 và nằm **ngoài mọi PR suốt 5 ngày** trong một
> worktree bám layout trước ADR-0011; tìm thấy khi dọn worktree (#298). Số cũ 0010 đã bị
> `0010-domain-allowlist-mang-sandbox.md` chiếm nên đánh lại thành **0016**. Ba thứ đã kiểm lại trước khi port,
> không chép nguyên: (1) đường dẫn package sau ADR-0011; (2) mọi số dòng được trích — `load_config` 378 → 410,
> adapter `claude-code` 878 → 923, `config.py:65` và hai chỗ gọi vẫn đúng; (3) con số cốt lõi, đo lại ở phần
> Bối cảnh. Dòng `Studio-creators` trong bảng đã **bỏ** — công ty đó bị gộp đi bởi chính ADR-0011; giai thoại
> `make eval-record` cho studio ở dưới giữ nguyên vì nó là chuyện đã xảy ra thật và vẫn là bằng chứng hợp lệ.
> **Đã cài đặt** (2026-09-15, PR #303): `may_config_file`/`_gop_tang`/`explain_config` ở
> `platform/xagents-core/src/xagents_core/llm.py`, lệnh `python -m company.probe --explain`, và
> `XAGENTS_LLM_CONFIG` đã vào `SECRET_ENV` của `sandbox.py`. Câu "chưa cài đặt" của bản port 09-14 nay sai,
> đã sửa tại chỗ thay vì để ADR nói một đằng mã chạy một nẻo.

## Bối cảnh

Câu hỏi khởi nguồn của chủ dự án: *"sao không tích hợp `llm.yaml` trong core, gọi model thông qua gateway?"*
Đo trước khi trả lời, và phép đo lật cả hai vế.

### `llm.yaml` đã ở core rồi — cái lặp lại là FILE, không phải MÃ

`load_config(core, path, cls)` (`platform/xagents-core/src/xagents_core/llm.py:410`) là chỗ duy nhất đọc nó;
`core.config_file` (`config.py:65-67`) trả `self.root / "llm.yaml"`. Mọi công ty gọi qua đúng hàm đó:

| Nơi gọi | File |
|---|---|
| `companies/software-company/src/company/llm.py:156` | `core_load_config(CORE, path, cls=LLMConfig)` |
| `companies/keeper/src/keeper/llm.py:62` | như trên |

Nên "đưa `llm.yaml` vào core" là việc **đã xong từ K3.3**. Thứ còn lặp là **nội dung file**: danh sách backend
(tài khoản, `config_dir`, `base_url`) được chép tay vào từng package.

### Vấn đề thật: cấu hình bốc hơi đúng chỗ agent làm việc

`llm.yaml` nằm trong `.gitignore` (gốc dòng 21 và 66, cộng `companies/software-company/.gitignore:5` — mọi
package có agent). Mà `AGENTS.md` cấm §2 bắt **mỗi phiên agent một `git worktree` riêng**. Hai luật đó cộng lại
cho kết quả đo được ngày 2026-09-09:

```
Claude-Agents (checkout chính)   2/3 llm.yaml
14 worktree khác                 0/3 llm.yaml
```

**14/16 worktree không có một file cấu hình model nào.** Đó không phải sự cố — đó là hệ quả tất yếu của thiết kế
hiện tại: file gitignored thì không đi theo `git worktree add`.

Đo lại ngày 2026-09-14 lúc port ADR này (số cũ 5 ngày rồi, không chép lại mà không kiểm): **0/4 worktree**, kể cả
**checkout chính**, có một `llm.yaml` nào. Vấn đề không tự lành theo thời gian — nó tệ đi, vì hai file còn sót ở
checkout chính hồi 09-09 nay cũng không còn. Nghĩa là ở trạng thái hiện tại không worktree nào chạy được model
thật cho tới khi có người dựng tay lại cấu hình.

Hậu quả đã trả giá hai lần, và cả hai lần đều bị chẩn đoán sai:

- Phiên trước, `make eval-record` cho studio lỗi CLI `error_max_turns`; kết luận ghi lại là *"studio không có
  `llm.yaml` thật ở máy này"*. Sai: file **có** ở checkout chính, chỉ thiếu ở worktree đang chạy.
- Phiên này, dựng eval cho `keeper`: subagent phải tự tạo `keeper/llm.yaml` trước khi ghi được bản ghi nào.

Cả hai lần, triệu chứng hiện ra ở tầng CLI/model nên người đọc đi tìm lỗi ở đó, trong khi nguyên nhân nằm ở
tầng cấu hình. Đây đúng khuôn `TRAPS.md` §2 (suy từ thông điệp lỗi thì sai) ở quy mô hạ tầng.

### Gateway không thay thế được — nó không nói cùng một giao thức

`platform/gateway/README.md`: daemon cục bộ nhận **OpenAI Chat Completions** rồi dịch sang Google Code Assist, xoay vòng
tài khoản Google Antigravity. Nhưng đường model mà chủ dự án vừa yêu cầu dùng là gói **subscription Claude**:

```yaml
- name: claude-liendv
  provider: claude-code          # xagents_core/llm.py:923 — adapter CLI
  config_dir: ~/.claude-liendv   # CLAUDE_CONFIG_DIR của một phiên `claude` đã đăng nhập
```

`claude-code` là **tiến trình con `claude -p`**, không phải HTTP. Gateway không có cách nào phục vụ nó mà không
tự biến thành trình quản lý tiến trình — và khi đó `make eval-record` lẫn CI đều mọc thêm một daemon phải chạy
mới làm việc được. Ép mọi thứ qua gateway là **bỏ mất đúng đường model rẻ nhất đang có**.

## Quyết định

**Tách cấu hình model làm hai tầng theo trục "thứ gì thuộc về MÁY" và "thứ gì thuộc về CÔNG TY".**

1. **Tầng máy** — một file ngoài repo, mặc định `~/.config/xagents/llm.yaml`, đè được bằng `$XAGENTS_LLM_CONFIG`.
   Giữ `backends`: tên, `provider`, `config_dir`, `base_url`, `models` theo tier. Đây là thứ phụ thuộc **máy này
   đang đăng nhập tài khoản nào**, không phụ thuộc công ty nào đọc nó.
2. **Tầng package** — `<package>/llm.yaml` như hiện nay, nhưng chỉ còn phần **khác nhau thật giữa các công ty**:
   `routing` (agent nào tier nào), ngân sách, `prices`, `sandbox`, `max_input_chars`.

`load_config` đọc tầng máy trước, rồi để tầng package đè lên, rồi biến môi trường đè lên trên cùng — giữ nguyên
thứ tự ưu tiên đang có, chỉ thêm một tầng nền ở dưới cùng.

**Gateway giữ nguyên vai trò**: một `backend` trong danh sách, dùng khi muốn xoay vòng tài khoản Google. Không
phải cửa duy nhất, và không được là phụ thuộc bắt buộc của đường eval.

### Vì sao không chọn ba phương án kia

| Phương án | Vì sao không |
|---|---|
| Mọi thứ qua gateway | Mất đường `claude-code` (CLI, không HTTP); thêm một daemon vào phụ thuộc của `eval-record` và CI |
| Chép/symlink `llm.yaml` khi tạo worktree | Bí mật bị nhân bản khắp đĩa; quên một lần là im lặng hỏng; không sửa được nguyên nhân |
| Commit `llm.yaml` vào repo | `AGENTS.md` cấm §3, và gitleaks quét cả lịch sử |

## Hệ quả

**Được**

- Worktree mới dùng được model ngay: đây là điều kiện để một phiên agent chạy `make eval-record` mà không phải
  dựng lại cấu hình — thứ vừa tốn hai phiên.
- Xoay tài khoản, đổi `config_dir`, thêm backend: sửa **một** chỗ thay vì ba.
- `llm.example.yaml` của từng package ngắn lại, và nói đúng thứ package đó thật sự quyết định.

**Mất / phải trả**

- Thêm một tầng nghĩa là thêm một câu hỏi "giá trị này đến từ đâu". Bắt buộc kèm một lệnh in ra **nguồn của
  từng khoá** (`python -m <pkg>.probe --explain` hoặc tương đương) — không có nó thì tầng nền thành một chỗ để
  cấu hình lặng lẽ khác với thứ người đọc thấy trong file package.
- File ngoài repo nằm ngoài mọi cổng CI. Phải có ca kiểm: thiếu file nền thì hành vi là **fail-closed và nói rõ
  thiếu gì**, không phải im lặng rơi về `provider: fake`.
- Đây là đường đọc bí mật thứ hai trên máy; `clean_env()` và `sandbox` phải được rà lại cho đúng họ (`AGENTS.md`
  bắt buộc §5).

**Không đổi**

- `provider: fake` vẫn là mặc định của test; `evals --replay` vẫn chạy offline, không đọc tầng nào.
- Thứ tự ưu tiên hiện có (file → biến môi trường) giữ nguyên.

## Liên quan

- ADR-0001 (lõi chung `xagents-core`) — `load_config` đã lên core từ K3.3; ADR này nói về **dữ liệu**, không phải mã.
- `AGENTS.md` cấm §2 (mỗi phiên một worktree) và cấm §3 (không commit `llm.yaml`) — hai luật đúng, giao nhau tạo ra
  chỗ trống này.
- `TRAPS.md` §2 (đo trước khi sửa): hai lần chẩn đoán sai đã dẫn ở phần Bối cảnh.
- `platform/gateway/README.md` — vai trò gateway sau ADR này: một backend, không phải cửa duy nhất.
