# Đối chiếu `seeker19110/projects-template` với repo này — 2026-09-14

Làm theo `docs/PROMPT-SHEET.md` §H (đọc repo/skill bên ngoài để học): chia ba cột **đã có và sâu hơn /
đã có nhưng nông hơn / chưa có**; với "chưa có" phải chỉ ra **sự cố ĐÃ XẢY RA ở đây** mà nó giải quyết,
không có thì xếp "chưa cần". Không cài gì; kết luận là sửa tài liệu/code của mình.

Nguồn đối chiếu: `seeker19110/projects-template` @ `main` (bộ khung tài liệu + script cho Claude Code:
`CLAUDE.md` 9 mục luật, `docs/framework/` 19 file, `.claude/commands/` 13 lệnh, `.claude/agents/` 11 vai,
`scripts/` 10 engine + 9 self-test).

Đo trên `claude-agents` @ `231b804` (HEAD `main` lúc đối chiếu).

## Cột 1 — Đã có ở đây và SÂU HƠN (không lấy gì)

| projects-template | Ở đây | Vì sao sâu hơn |
|---|---|---|
| Quy trình 9 giai đoạn + cổng giữa giai đoạn (tài liệu) | Máy trạng thái gate chạy thật: `orch/ticket_fsm.py`, `orch/release_fsm.py`, `gates_flow.py`, 5 kind gate (spec/plan/release/acceptance/escalation) + `gate_cli` | Cổng ở kia là câu chữ trong tài liệu, ở đây là bảng chuyển có test và có ADR-0034 canh |
| Feature gate "Approved for implementation" trong `docs/specs/*.md` | Gate `spec` là gate người ký thật, có hồ sơ bằng chứng (`gate_brief.py`, `/gate-brief`) | Bên kia kiểm bằng grep chuỗi trong PR; ở đây là trạng thái trong bus, không tự khai được |
| Điều phối 3 tầng + nhãn `route:` | `/thi-hanh` + `docs/KHUON-THI-HANH.md` + `routing.py` + 10 subagent `sc-*` sinh từ nguồn (`make subagents`) | Bên kia subagent viết tay, dễ lệch; ở đây bản dẫn xuất có cổng `subagents check` |
| Goal loop nhiều PR + "cùng một failure sửa tối đa 3 lần → BLOCKED" | `AGENTS.md` luật bắt buộc 6 (vá 3 lần lòi lỗi mới ⇒ dừng, là kiến trúc sai) + `docs/thi-hanh/<mã>.md` làm file trạng thái | Cùng một luật, nhưng ở đây gắn với file trạng thái có thật đang dùng |
| `/maintain` + `scripts/maintenance-sweep.sh` (quét 6 mảng mục nát) | `companies/keeper/` — cả một công ty bảo trì, khách hàng số 0 là chính repo này, có `keeper.cli drift` | Một script vs một pipeline có agent, eval, PR |
| `docs/framework/quality-gates-by-profile.md` (cổng theo loại dự án) | `stacks.py` — `detect()` + `run_checks` theo stack thật của repo khách (node/maven/…); ADR-0013 | Bên kia là bảng tra cho người đọc; ở đây là code chọn lệnh kiểm đúng stack |
| `docs/framework/03-tech-selection` (research-first chọn công nghệ) | `skills/tech-evaluation.md` (tiêu chí viết trước khi nhìn công cụ, TCO 24 tháng, spike có timebox) + `skills/domain-research.md` | Bên kia là hướng dẫn; ở đây là skill có `version`, golden, eval |
| `industry-standards.md`, `quality-supplements-*` (a11y, mobile, i18n, privacy…) | 48 skill trong `companies/software-company/skills/` — đúng các chủ đề đó, mỗi skill có chủ sở hữu (ADR-0016) | Bao phủ rộng hơn và có cổng `assetscan` canh |
| `CONTEXT.md` (sổ tay thuật ngữ) | `docs/NGON-NGU.md` | Tương đương |
| `TRAPS.md`, `CODEMAP.md`, `AGENTS.md`, ADR, conventional commits, cấm push `main`, PR template, ruleset | Đã có đủ, và có cổng CI canh (`test_cong_repo.py`, `pr-policy.yml`, `.github/rulesets/main.json`) | Bên kia phần lớn là quy ước trong tài liệu |
| Kỷ luật test (khuyến nghị TDD cho code mới) | `AGENTS.md` luật bắt buộc 4: TDD **cứng** cho mọi code + `fail_under = 100` cả năm package | Nghiêm hơn hẳn |
| Báo cáo trung thực | `AGENTS.md` luật cấm 8 (5 bước bằng chứng) + `verified_by=workspace\|orchestrator` do máy sinh | Bên kia là lời hứa; ở đây có trường dữ liệu |

## Cột 2 — Đã có nhưng NÔNG HƠN ở một điểm cụ thể

| Điểm | Hiện trạng ở đây | Chỗ bên kia nhỉnh hơn |
|---|---|---|
| Chẩn đoán bug khó | `docs/PROMPT-SHEET.md` §B + `TRAPS.md` §2 | `/debug` của bên kia đặt **Pha 0: dựng feedback loop đỏ-được TRƯỚC khi ra giả thuyết** thành bước bắt buộc riêng. Ở đây "tái hiện được" nằm lẫn trong một đoạn văn §B |
| Sức khỏe kiến trúc | 8 phép đo A1–A8 trong `docs/TASK-PACK.md`, chạy tay mỗi lần audit | `scripts/arch-health-radar.sh` cho **một điểm số chạy được bằng script**, dùng được trong CI. Ở đây mọi phép đo phụ thuộc người ngồi chạy |

## Cột 3 — CHƯA CÓ, và có sự cố tương ứng đã xảy ra ở đây

### 3.1. Vòng hội tụ cho audit — ĐÃ CÓ ĐỦ, KHÔNG LẤY (đính chính hai lần)

Dự thảo đầu xếp đây là khe hở lớn nhất. Đọc kỹ `docs/TASK-PACK.md` thì **cả cơ chế lẫn yêu cầu đều đã có**:

- Sổ hội tụ: §"Việc để lại đang treo" — "mỗi phiên audit **đọc sổ này trước, cập nhật nó sau**; đóng được
  dòng nào thì xoá dòng đó kèm số PR trong CHANGELOG". Ba dòng đang treo (09-12, 09-13) đều có lý do đo được.
- Yêu cầu để lại bằng chứng: gói việc audit mục 2 đã có ô kiểm — *"'Việc để lại' của báo cáo **lần trước**
  được chép lại kèm trạng thái: đã đóng ở PR nào, hay còn treo"*.

Chênh lệch còn lại so với `COMPREHENSIVE-AUDIT-STATUS.md` bên kia chỉ là trạng thái thứ ba ("cố ý bỏ") và
việc bảng đó nằm ở đầu báo cáo thay vì cuối — **thuần hình thức, không ứng với sự cố nào**. Theo §H, xếp
"chưa cần". Không sửa `docs/TASK-PACK.md` trong PR này.

### 3.2. Khuôn "Báo cáo xác thực" cố định trước commit/merge — ĐỀ NGHỊ LẤY

- **Bên kia có gì**: `CLAUDE.md` §7 — một khối văn bản cố định (`Build ✅/❌ | Type … | Lint … | Test X/Y`,
  `Test tái hiện (nếu là fix) ✅/❌/n-a`, `KẾT LUẬN: Sẵn sàng / Cần xử lý`), bất kỳ ❌ là cấm commit.
- **Sự cố tương ứng ở đây**: `AGENTS.md` luật cấm 8 đã mô tả đúng 5 bước, nhưng bước 4 ("output có khớp câu
  định nói không") **không có vật thể nào để đối chiếu** — nó nằm trong đầu người/agent. Đó chính là lỗ mà
  luật cấm 8 được viết ra để bịt, và `TRAPS.md` §6 ("câu tự biện hộ trước khi né luật") cho thấy nó vẫn bị né.
  Một khuôn điền-vào-chỗ-trống biến bước 4 thành việc cơ học.
- **Lấy dưới dạng nào**: một khối khuôn ngắn thêm vào `AGENTS.md` luật cấm 8, dùng **lệnh thật của repo này**
  (`make lint` / `make test` / `make cov` / `evals --replay --strict` / `subagents check` / `assetscan scan`),
  cộng dòng `Test đỏ trước khi sửa (luật 4, đo hai chiều) ✅/❌`. Không thêm lệnh `/gate` riêng — `make` đã là
  cổng, thứ thiếu là *khuôn báo cáo*, không phải trình chạy.

## Cột 3b — CHƯA CÓ nhưng CHƯA CẦN (không có sự cố tương ứng)

| Thứ | Vì sao chưa cần |
|---|---|
| `/grill` (phỏng vấn dồn dập làm rõ yêu cầu) | **Ngược luật ở đây**: `AGENTS.md` "Khi bối rối" bắt nêu giả định rồi đi tiếp, chỉ dừng hỏi trong 4 trường hợp. Lấy vào sẽ tạo mâu thuẫn luật |
| Bảng làm rõ yêu cầu mơ hồ (`CLAUDE.md` §1b bên kia: "tối ưu"/"kiểm tra lỗi" → trình lựa chọn) | Repo này chỉ có 2 lệnh người dùng (`/gate-brief`, `/thi-hanh`) — chưa đủ lệnh để mơ hồ. Xem lại khi số lệnh > 5 |
| `PROGRESS.md` (một file trạng thái toàn dự án) | Đã thay bằng `docs/sessions/<ngày>.md` + `docs/thi-hanh/<mã>.md`; thêm file thứ ba chỉ tạo chỗ lệch |
| `/bootstrap`, `/consult`, `copy-framework.sh` | Dành cho việc *dựng dự án mới từ khung*. Repo này không phát hành khung cho người khác chép |
| `scripts/telemetry-log.sh` + `model-rates.json` (đo chi phí AI) | `platform/gateway` + `metrics.py` đã nắm chỗ này; chưa có sự cố về chi phí được ghi lại |
| `/audit-optimize`, `/completion`, `/ui-ux`, `/incident`, `/adr` (dạng slash command) | Nội dung tương ứng đã có ở `skills/` (48 skill), `templates/` (15 mẫu), `docs/TRUC-VA-DUNG-KHAN.md`. Thiếu duy nhất lớp vỏ lệnh — chưa có sự cố nào do thiếu vỏ |
| `arch-health-radar` (cột 2) | Đề nghị **hoãn**: đưa 8 phép đo thành script là việc đáng làm, nhưng đó là PR riêng có test (`fail_under = 100`), không phải "lấy từ repo kia" |

## Kết luận

`projects-template` là **bộ khung tài liệu** cho một phiên Claude Code; repo này là **hệ chạy thật có bus,
gate, eval và 100% coverage**. Trên 13/15 hạng mục đối chiếu, repo này đã sâu hơn. Bê nguyên bộ khung sang
sẽ tạo tài liệu song trùng và mâu thuẫn luật (rõ nhất ở `/grill`).

**Đề nghị lấy đúng MỘT thứ** — sửa tài liệu, không thêm code, không thêm cổng CI, không thêm file:

1. `AGENTS.md` luật cấm 8 — thêm khuôn Báo cáo xác thực điền-vào-chỗ-trống bằng lệnh thật của repo (§3.2).

Ứng viên thứ hai (vòng hội tụ audit) đã bị chính đối chiếu này loại ở §3.1: cơ chế đã có đủ.

Con số cuối: trong ~25 hạng mục của `projects-template`, **1 thứ đáng lấy**. Đó là kết quả có ý nghĩa, không
phải kết quả rỗng — nó nói repo này đã đi trước bộ khung kia gần như mọi mặt, và xác nhận §H làm đúng việc
của nó: chặn một đợt bê tài liệu song trùng vào repo.
