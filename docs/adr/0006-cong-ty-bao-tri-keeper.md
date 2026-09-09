# ADR-0006: Công ty con `keeper` — bảo trì toàn dự án

## Bối cảnh

Bảo trì X-Agents hiện là việc của **người**, rải rác và không ai sở hữu:

- Dependabot (`.github/dependabot.yml`) mở PR nâng version, nhưng không ai gộp, không ai kiểm
  `fail_under = 100` trước khi nó đỏ, và nó mở nhiều PR song song — vi phạm luật "một PR mở tại một thời điểm"
  (`docs/QUY-TRINH-GIT.md` §2c).
- Bản dẫn xuất (`.claude/agents/sc-*.md`, `tests/golden/`) lệch nguồn thì chỉ CI mới bắt, và chỉ khi ai đó
  vô tình chạm vào. Không có ai *đi tìm* chỗ lệch.
- Nợ tài liệu (`CHANGELOG.md`, `docs/sessions/`, số liệu `README.md`) đã phải thành luật bắt buộc
  (`AGENTS.md` §10) vì đã quên nhiều lần — luật là cách vá thủ công cho một việc lẽ ra tự động được.
- `TRAPS.md` chỉ lớn lên khi có người nhớ ghi. Bài học lặp lại vẫn lặp lại.
- Ba tín hiệu sức khoẻ không ai đo: test flaky, thời gian CI, độ trôi coverage giữa năm package.

Ngoài repo, hệ sinh thái open-source đã có sẵn từng mảnh: Renovate (nâng dependency), release-please
(CHANGELOG + version), OpenSSF Scorecard (chính sách bảo mật), `qodo-ai/pr-agent` và
`anthropics/claude-code-action` (agent LLM sửa code trong PR), `actions/stale`, Mergify. Mỗi cái làm tốt một
việc và **không cái nào biết luật của repo này** — không biết checklist 7 bước ở `CONTRIBUTING.md` §3, không
biết "test phải đo hai chiều", không biết "không hạ `fail_under`".

Đó đúng là hình dạng một công ty: nhiều vai chuyên môn, một luật chung, một người điều phối.

## Quyết định

Dựng package thứ sáu của workspace: **`keeper/`** (distribution `keeper`, package Python `keeper`),
là công ty con **bảo trì** — khách hàng đầu tiên và mặc định của nó là chính repo X-Agents.

Nó **không viết lại** Renovate/CodeQL/Scorecard. Nó *tiêu thụ* đầu ra của chúng làm tín hiệu, rồi làm phần mà
không công cụ nào ngoài kia làm được: quyết định **cái gì đáng sửa, sửa theo luật của repo này, và chứng minh
đã sửa**.

### Cấu trúc — 6 khối, 8 agent, 1 human gate

| Khối | Agent | Việc |
|---|---|---|
| `watch` | `dependency-scout` | Đọc Dependabot/Renovate/CVE/EOL; phân loại nâng version theo bán kính ảnh hưởng |
| `watch` | `health-monitor` | Đo flake rate, thời gian CI, độ trôi coverage, kích thước repo, tuổi PR |
| `watch` | `drift-detector` | Tìm lệch: bản dẫn xuất vs nguồn, `CODEMAP.md`/`ARCHITECTURE.md` vs cây thật, PR merged thiếu dòng `CHANGELOG.md` |
| `triage` | `triager` | Gom tín hiệu → ticket bảo trì có `risk_tier`; gộp trùng; hoãn thứ chưa đáng kèm ngày đáo hạn |
| `engineering` | `patcher` | Sửa thật trên worktree riêng: nâng version, vá lint/type, `make golden`/`make subagents`, vá tài liệu |
| `engineering` | `refactorer` | Nợ kỹ thuật có ADR. Chỉ chạy khi được giao rõ, không tự khởi động |
| `quality` | `regression-guard` | Chạy đúng lệnh CI; ép **đo hai chiều**; rà cả họ lỗi (`AGENTS.md` bắt buộc §5) |
| `quality` | `security-auditor` | gitleaks toàn lịch sử, audit dependency, OpenSSF Scorecard, quét bí mật trong artifact |
| `release` | `release-clerk` | Dòng `CHANGELOG.md`, `docs/sessions/<ngày>.md`, số liệu `README.md`, tag — **trong chính PR** |
| `supervisor` | `keeper-supervisor` | Hạn mức token/PR, chống bão PR, giữ luật một-PR-mở, dừng khẩn |

Human gate mới: **`keeper`** — chỉ mở cho ticket `risk_tier` cao. Tier thấp đi thẳng tới auto-merge.

### Tính năng nâng cao (phần khác biệt so với ghép công cụ rời)

1. **Bậc rủi ro tự động (`risk_tier`)** — tính từ bán kính ảnh hưởng: patch version của dev-dependency là
   `low` (tự merge); major version, chạm `xagents-core`, chạm `agents/`/`skills/`, hay chạm CI là `high`
   (bắt buộc gate `keeper` + ADR nếu là kiến trúc).
2. **Bằng chứng đo hai chiều bắt buộc** — `regression-guard` phải nộp output *tắt bản sửa → test đỏ* và
   *bật lại → xanh*. Không có bằng chứng thì ticket không rời pha quality. Đây là `AGENTS.md` bắt buộc §4
   biến thành cổng máy, không còn là lời hứa.
3. **Ngân sách thay đổi (change budget)** — trần N PR bảo trì mỗi tuần và **đúng một PR mở tại một thời
   điểm**, khớp `docs/QUY-TRINH-GIT.md` §2c. Vượt trần thì xếp hàng, không mở thêm.
4. **Sổ nợ có đáo hạn (debt ledger)** — mọi thứ `triager` hoãn đều mang ngày đáo hạn; quá hạn thì escalate.
   Tái dùng cơ chế `debt_due` đã có ở `software-company`, không dựng mới.
5. **Rà cả họ lỗi thành pha bắt buộc** — sau mỗi patch, `regression-guard` grep mọi chỗ dùng cùng cơ chế và
   báo cáo **cả chỗ an toàn và vì sao** (`TRAPS.md` §1). Kết quả đính kèm PR.
6. **Tự đề xuất `TRAPS.md`** — gặp cùng khuôn lỗi lần thứ hai, `keeper-supervisor` sinh sẵn một mục
   `TRAPS.md` cho người duyệt. Bài học thành tài sản của repo, không của một phiên.
7. **Cầu GitHub chỉ-đọc (adapter)** — `gh api` đọc Dependabot alert, CodeQL alert, trạng thái check, tuổi PR.
   Không quyền ghi ngoài việc mở PR qua đúng quy trình nhánh.
8. **Chạy khô và phát lại** — mọi phiên bảo trì đi qua sqlite bus của `xagents-core`, resume được sau khi
   dừng; `--dry-run` in kế hoạch thay đổi mà không chạm file.
9. **Canary trên chính mình** — X-Agents là khách hàng số 0. Chỉ sau khi công ty này bảo trì được chính repo
   mình trong một chu kỳ mới mở cho repo khách của `software-company`.
10. **Mặc định model tier thấp** — bảo trì là việc lặp, tốn ít suy luận. `strong` chỉ dành cho `refactorer`
    và cho `triager` khi `risk_tier=high`.

### Không làm

- Không thay Dependabot/CodeQL bằng bản tự viết.
- Không tự xoá dead code (`AGENTS.md` cấm §7) — chỉ báo cáo.
- Không hạ `fail_under`, không sửa ruleset, không push `main`.
- Không tự nâng major version của `xagents-core` khi hai công ty còn đang chuyển theo bảy bước K3.

## Hệ quả

**Được:** một chủ sở hữu cho việc bảo trì; luật repo thành cổng máy thay vì lời nhắc trong `AGENTS.md`;
tín hiệu sức khoẻ được đo thay vì đoán; `xagents-core` có khách hàng thứ ba, ép nó thật sự trung lập.

**Mất:** package thứ sáu phải đạt `fail_under = 100` như năm cái kia; thêm một human gate cần người trực;
nguy cơ công ty bảo trì tự tạo nhiễu PR — chính vì thế mới có ngân sách thay đổi (mục 3).

**Rủi ro lớn nhất:** agent bảo trì "sửa" thứ không hỏng. Chặn bằng ba lớp: `risk_tier`, bằng chứng đo hai
chiều, và luật cấm sửa code cạnh bên.

**Lộ trình:** 9 PR (BT0–BT8, đặc tả chi tiết ở `keeper/docs/DAC-TA-KEEPER.md`) — (1) khung package + pyproject + CI, (2) `watch` + adapter GitHub chỉ-đọc, (3) `triage`
+ sổ nợ + ngân sách thay đổi, (4) `engineering` + `quality` + bằng chứng hai chiều, (5) `release` + gate
`keeper` + console. Mỗi PR tự đứng được và giữ coverage 100%.

## Liên quan

- ADR-0001 `docs/adr/0001-loi-chung-xagents-core.md` — lõi chung; công ty này xây thẳng trên `xagents_core`,
  không sao chép mã từ `company`/`studio`.
- `AGENTS.md` cấm §3/§6/§7, bắt buộc §1/§4/§5/§10 — công ty này là bản thi hành máy của các luật đó.
- `docs/QUY-TRINH-GIT.md` §2c — một PR mở tại một thời điểm; ngân sách thay đổi phải tôn trọng.
- `CONTRIBUTING.md` §3 — checklist 7 bước; `patcher` phải chạy đủ khi chạm `agents/`/`skills/`.
- `TRAPS.md` §1, §2 — rà cả họ lỗi, đo trước khi sửa; thành pha bắt buộc, không còn là thói quen.
