# ADR gốc 0024: một phiên Claude độc lập được mở lại ticket bị chặn — actor riêng có chữ ký, không giả `human:*`

Ngày: 2026-09-26 · Trạng thái: **được chấp nhận** 2026-09-26 (lựa chọn ở mục "Quyết định đã chốt"; code #348) · Sửa: ADR-0043 (software-company) §1
("`escalation` KHÔNG tự duyệt") · Liên quan: ADR gốc 0023 (F1: actor trên bus là chuỗi tự khai), ADR gốc 0020 (chữ ký
Ed25519 cho receipt)

Chủ dự án yêu cầu ngày 2026-09-26: *"phiên chính sẽ thay người duyệt, đủ độc lập với công ty và khách quan"*.
ADR này đo yêu cầu đó, giữ phần đúng của nó (phần lớn gate hôm nay là việc máy làm được) và sửa phần không
đứng được (phiên chính không độc lập, và một chuỗi actor không chứng minh được ai đã quyết).

## Bối cảnh

### 1. Gate hôm nay: toàn bộ quyết định là của người, và phần lớn chỉ là "chạy lại"

Đo trên `companies/software-company/company.sqlite` thật (dự án CAMPUS-UNI-20260922), chỉ đọc:

| Loại gate | Đã quyết | Người quyết | Quyết định | Chờ (giờ): trung vị / tối đa |
|---|---|---|---|---|
| `spec` | 1 | người | approve 1 | 0,04 / 0,04 |
| `escalation` | 13 | người | approve 11 · reject 2 | 0,08 / 27,66 |
| `release`, `acceptance` | 0 | — | — | — |

- **11/13** escalation đã quyết là `approve`, và lý do của cả 11 đều ghi `decision: retry|reopen`, tức là "cho
  chạy lại" chứ không phải chấp nhận rủi ro. Đây đúng là câu hỏi kiểm của `companies/software-company/TRAPS.md`
  ("duyệt gate này người có gõ gì ngoài retry không?").
- Lúc viết ADR có **4 gate `escalation` đang chờ**: TCK-011, TCK-015, REL-004, REL-005. Cả bốn đã chờ khoảng 34
  giờ, và 32 ticket phụ thuộc đứng theo hai gate ticket.
- Code có **14** lời gọi `request_gate(`: 1 `spec`, 1 `release`, 1 `acceptance`, 11 `escalation`.

### 2. Yêu cầu "phải là người" được thi hành ở đâu

| Chỗ | Kiểm gì | Không kiểm gì |
|---|---|---|
| `xagents_core/gates.py:87` `HumanGate.decide` | four-eyes (`created_by != by`); allowlist `COMPANY_GATE_APPROVERS` nếu đặt (đang **không** đặt) | không kiểm `is_human` |
| `xagents_core/gate_cli.py:33` `trusted_decision` | lúc replay, chỉ tin `gate.decide` có `env.actor` là người (`is_human`) và trùng `by`, hoặc actor hệ thống đóng gate `UAT-*` | — |
| `company/gate_cli.py:42` `trusted_autoapprove` | nhánh tin cậy RIÊNG của company: actor `"code"` + tiền tố lý do + cờ `COMPANY_GATE_AUTOAPPROVE` (ADR-0043) | — |
| `company/orch/cli_cmds.py:35` | CLI orchestrator chỉ nhận actor người | — |

Vậy "người" chỉ là một **tiền tố chuỗi** (`human:`). ADR gốc 0023 đã đo rằng mã khách chạy dưới `SubprocessSandbox`
ghi được `gate.decide` mang actor `human:*`, và gate được duyệt. Mọi actor mới chỉ dựa vào tên cũng sẽ có đúng
lỗ đó.

### 3. Vì sao phiên chính không phải người duyệt độc lập

Đo từ phiên 2026-09-26 (`docs/sessions/2026-09-26.md`):
- Chính phiên này viết #345 (sửa cách tính retry), chẩn đoán TCK-011/015, và soạn nguyên văn hint cho cả hai.
- Duyệt hai gate đó là **tự duyệt việc của mình**, đúng thứ four-eyes cấm. Lệnh `gate_cli approve --by human:client`
  do phiên này gõ cũng đã bị bộ phân loại quyền của môi trường chặn với lý do *Self-Approval*.
- Độc lập là tính chất của **quan hệ** giữa người quyết và việc được quyết, không phải của một phiên. Một phiên
  điều phối công ty (sửa code, viết hint, đọc bus) luôn là tác giả của một phần việc nó sẽ duyệt.

## Quyết định

### 1. Một actor mới, không phải người: `reviewer:<id>`

- Thêm nhánh tin cậy `trusted_reviewer` ở `company/gate_cli.py`, cùng khuôn `trusted_autoapprove`.
- `trusted_decision` của core **không đổi**: nó vẫn chỉ tin người. `is_human("reviewer:x")` là `False`, nên mọi chỗ
  "chỉ người" hiện có (ký spec, ghim profile, CLI orchestrator) tự động vẫn đóng với reviewer.

### 2. Tin theo chữ ký, không theo tên

- Mỗi quyết định của reviewer mang chữ ký **Ed25519** trên
  `(subject_id, thế hệ gate, decision, reason, sha256 của hồ sơ gate_brief đã đọc)`.
- Registry chỉ chứa **public key**, dùng lại hạ tầng của ADR gốc 0020 (`key_id`, `not_after`, xoay khoá).
- Khoá bí mật nằm ngoài mọi tiến trình ghi được bus: không trong worktree khách, không trong env của builder
  hay sandbox.
- Thiếu chữ ký, sai chữ ký, hết hạn, hay hash hồ sơ không khớp: không tin, và gate vẫn chờ.
- Đây là chỗ khác nhau giữa ADR này và yêu cầu nguyên văn: chuỗi `reviewer:*` tự nó không chứng minh gì (bài học F1).

### 3. Độc lập được thi hành bằng code, không bằng lời hứa

- Reviewer là một **tiến trình riêng, dựng mới cho mỗi gate**. Nó chỉ nhận hồ sơ `gate_brief`, không có tool
  ghi, không có lịch sử phiên điều phối.
- Code từ chối quyết định của reviewer khi:
  - (a) `key_id` của reviewer trùng khoá đã ký bất kỳ PR, hint hay receipt nào của chính ticket đó; hoặc
  - (b) hint đang dùng của ticket do cùng `key_id` viết.
- Four-eyes cũ (`created_by != by`) vẫn giữ nguyên.

### 4. Phạm vi: chỉ những quyết định mà người hôm nay chỉ gõ "chạy lại"

| Gate | Reviewer được | Reviewer không được |
|---|---|---|
| `escalation` ticket | `approve` = mở lại kèm hint (mỗi ticket tối đa N lần, rồi về người) | `reject` = đóng ticket |
| `escalation` dự án (stall/unhandled) | `approve` = chạy lại event | `reject` = đóng dự án |
| `escalation` release | không | `approve` = chấp nhận finding rồi giao; `reject` = đá ticket về làm lại |
| `spec`, `release`, `acceptance` | không (spec giữ người; release/acceptance theo ADR-0043) | — |

Mọi quyết định reviewer không được ra (hoặc không đủ bằng chứng để ra) thì **hold**: gate tiếp tục chờ người.
Không có đường nào để reviewer chấp nhận rủi ro thay khách.

### 5. Công tắc và dấu vết

- Cờ `COMPANY_GATE_REVIEWER`, mặc định tắt, đọc lại mỗi lần `apply()` như `COMPANY_GATE_AUTOAPPROVE`.
- Mỗi quyết định ghi `gate.decide` với actor `reviewer:<id>` kèm chữ ký. `status`, console và `gate_brief` hiện rõ
  "máy duyệt", không trộn với người.
- Người `reject` hay `rollback` sau đó thì luôn thắng, giống `acceptance.overridden` ở ADR-0043 §3.

## Phương án đã loại

**(e) Phiên chính ký thẳng bằng `human:client`.** Rẻ nhất: không phải viết code. Loại vì:
- đó là đóng vai người: ADR gốc 0023 F1 đo được chính khe này;
- phiên chính là tác giả của phần việc cần duyệt (mục 3 của Bối cảnh);
- môi trường đã từ chối nó (*Self-Approval*).

**(f) Actor `reviewer:*` chỉ dựa vào tên, không chữ ký.** Chỉ cần sửa một nhánh `trusted_*`. Loại vì bất kỳ tiến
trình nào ghi được bus (mã khách qua `SubprocessSandbox`, ADR gốc 0023) cũng tự khai được `reviewer:*`. Tác động giống
hệt F1, nhưng giờ còn được mở lại ticket.

**(g) Reviewer được mọi gate, gồm spec và chấp nhận finding của release.** Hết chờ người hoàn toàn. Loại vì chấp
nhận rủi ro thay khách (license, security block, phạm vi spec) là quyết định giá trị, không phải kiểm bằng chứng.
ADR-0043 đã chốt spec cần người, và sàn chất lượng là con đường tự động duy nhất cho release.

**(h) Không có reviewer; tiếp tục cắt escalation ở nguồn** (như #345 làm với `error_max_turns`). Không thêm bề mặt
tin cậy nào, và mỗi khuôn cắt được là vĩnh viễn. Không loại hẳn: đây vẫn là đường chính, reviewer chỉ phủ phần
còn lại. Nhưng nó không trả lời được yêu cầu của chủ dự án về 34 giờ chờ.

**(i) Đặt `COMPANY_GATE_APPROVERS` thành một tên máy.** Allowlist có sẵn, chỉ cần cấu hình. Loại vì allowlist chỉ
lọc tên, không có chữ ký, không có phạm vi theo loại gate, và `trusted_decision` vẫn không tin actor không phải
người khi replay. Quyết định sẽ mất sau một lần restart (bẫy "state chỉ sống trong RAM").

## Hệ quả

- **Phải sửa:**
  - `company/gate_cli.py`: thêm `trusted_reviewer`, gọi sau `trusted_autoapprove`.
  - `company/orch/gates_flow.py::_on_escalation_decided`: nhận decision của reviewer theo bảng phạm vi.
  - Một lệnh mới để dựng tiến trình reviewer: đọc `gate_brief`, ký, ghi `gate.decide`.
  - Registry public key (dùng lại ADR gốc 0020).
  - `SECURITY.md`, `docs/TRUC-VA-DUNG-KHAN.md` (mục "máy duyệt").
  - ADR-0043 §1 đổi thành "escalation chỉ người hoặc reviewer có chữ ký theo ADR gốc 0024".
- **Không đổi:** core (`trusted_decision`, `HumanGate`), `spec`, sàn ADR-0043, four-eyes.
- **Khó hơn:** vận hành thêm một khoá. Mất khoá thì reviewer tắt, gate quay về người. Lộ khoá thì xoay theo ADR gốc 0020.
- **Chưa đóng được:** F1 của ADR gốc 0023 (người thật cũng chỉ là chuỗi `human:*`) vẫn mở. ADR này không làm nó tệ
  hơn, vì reviewer không đi qua đường tin theo tên, nhưng cũng không sửa nó.
- **Môi trường:** bộ phân loại quyền của Claude Code có thể vẫn chặn một phiên agent chạy lệnh duyệt. Muốn tiến
  trình reviewer chạy tự động thì chủ dự án phải tự thêm luật quyền cho đúng lệnh đó. Không agent nào tự làm việc này.
- **Dấu hiệu quyết định này sai:** `reopen` của reviewer mà ticket lại `blocked` với cùng khuôn lỗi (đo bằng
  `diagnose`, `ticket_quay_vong`). Tỉ lệ đó vượt tỉ lệ của người (hôm nay 2/13 escalation cần `reject`) thì phải
  thu hẹp phạm vi hoặc tắt cờ.

## Quyết định đã chốt (2026-09-26)

Chủ dự án giao phiên chính chọn (*"bạn tự quyết cho nó hoạt động ổn định đi"*). Phiên chọn cũng là phiên viết
code — lựa chọn nào nghiêng về an toàn hơn thì lấy cái đó, để người đọc sau không phải tin phán đoán của nó.

| Câu | Chọn | Vì sao |
|---|---|---|
| 1. Phạm vi | **S2**: `approve` escalation ticket (`decision:reopen\|close`) và dự án (`decision:retry\|close`) | Đúng phần "chạy lại" đo được (11/13); không đụng release/spec/nợ kiến trúc |
| 2. Trần | **1 lần mỗi subject** | Lần sau về người ⇒ reviewer không bao giờ duyệt lại hint của chính nó |
| 3. Khoá | File ngoài repo: khoá bí mật `~/.config/xagents/gate-reviewer/<tên>.pem`, registry `~/.config/xagents/gate-reviewers.json` (`COMPANY_GATE_REVIEWER_REGISTRY`) | Cùng khuôn registry ADR gốc 0020 |
| 4. Chạy | **Theo lệnh**: một phiên Claude tách riêng chạy `/gate-review` | Không cần luật quyền mới cho một tiến trình tự chạy; người bật được, tắt được |
| 5. Bốn gate đang chờ | Không đổi — vẫn của người | Lệnh duyệt đã bị chặn *Self-Approval*; không đi đường khác tới cùng kết quả |

### Điểm lệch so với mục Quyết định ở trên (code thật, `companies/software-company/src/company/gate_reviewer.py`)

- **§3 (loại tác giả theo `key_id`) không làm**: PR và hint của công ty không mang chữ ký, nên không có gì để so.
  Thay bằng trần 1 lần mỗi subject (đạt cùng mục đích: reviewer không duyệt hint nó viết) cộng quy trình của skill
  `/gate-review` (phiên mới, chỉ đọc hồ sơ, không phải phiên điều phối).
- **"Tiến trình riêng, không tool ghi" là quy trình, không phải code**: CLI không biết nó được gọi từ phiên nào.
  Code chỉ bảo đảm chữ ký, phạm vi, thế hệ, trần, cờ.
- **Cờ đọc cả lúc áp** (như `COMPANY_GATE_AUTOAPPROVE`): tắt cờ rồi mở lại tiến trình thì quyết định cũ của
  reviewer không được áp — gate hiện lại chờ người. Hỏng thì đóng, đổi lại vài gate phải duyệt lại.
- **Thu hồi khoá**: đặt `not_after` về hiện tại trong registry — quyết định ký trước mốc đó vẫn hợp lệ; xoá hẳn khoá
  thì mọi quyết định cũ của nó thôi được tin (gate hiện lại chờ người).
- **Trần đã biết của khoá**: cùng user OS thì mã khách chạy qua `SubprocessSandbox` đọc được file khoá, đúng như F1
  (ADR gốc 0023). Chỉ ADR gốc 0023 (sandbox không tụt ngầm) đóng được; tới lúc đó, bật reviewer chỉ nên cùng
  sandbox container.

## Câu hỏi cho người (bản gốc lúc Proposed — đã trả lời ở trên)

1. **Phạm vi:**
   - S1: chỉ `escalation` ticket (mở lại);
   - S2: S1 cộng `escalation` dự án (chạy lại event);
   - S3: như bảng mục 4 nhưng cho reviewer thêm `reject` release, tức đá ticket về làm lại (không bao giờ `approve`).
2. **Trần mở lại** của reviewer mỗi ticket trước khi bắt buộc về người: 1, 2 hay 3?
3. **Khoá reviewer để ở đâu:** file ngoài repo (như registry receipt của ADR gốc 0020), hay kho khoá của hệ điều hành?
4. **Chạy tự động hay theo lệnh:** reviewer tự chạy khi gate mở (cần bạn thêm luật quyền), hay bạn gõ một lệnh để
   giao gate cho reviewer?
5. **Bốn gate đang chờ hôm nay** (TCK-011, TCK-015, REL-004, REL-005) không nằm trong ADR này, và vẫn cần bạn duyệt
   bằng hai lệnh ghi ở `docs/sessions/2026-09-26.md`, mục "Bốn gate đang chờ". ADR có hiệu lực cho gate mở **sau** khi nó được chấp
   nhận và code xong.
