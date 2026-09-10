# ADR-0003: đối chiếu `ruvnet/ruflo` — lấy một nghi thức, từ chối phần còn lại

Ngày: 2026-09-07 · Trạng thái: **được chấp nhận** (người dùng duyệt 2026-09-07: "lấy những gì hữu ích đi") · Liên quan: ADR-0001 (K3)

> Số 0002 ở thư mục này đã được ADR-0001 §"Liên quan" đặt trước cho `0002-bus-phien-ban-va-doc-luoi.md` (K4),
> nên ADR này lấy 0003.

## Bối cảnh

`ruvnet/ruflo` (trước là `claude-flow`) giải cùng bài toán với repo này — điều phối nhiều agent LLM thành một
đơn vị làm việc — ở quy mô lớn hơn hai bậc về mức chú ý (71k sao). Câu hỏi của ADR này hẹp: **cơ chế nào của nó
có ích cho dự án này**, và cơ chế nào phải từ chối kèm lý do ghi lại để phiên sau không đọc lại 847k dòng rồi
kết luận y hệt.

Đo trên bản clone `--depth 50` tại `277c7bc0` (2026-09-05), không lấy từ README của họ; lệnh đo trong thân PR:
5.628 file theo git, ~847.000 dòng TS/JS nguồn (trừ `node_modules`, `dist`), 577 file test, 91 ADR, 523 file
`.md` định nghĩa agent, 28 workflow CI, và **ngưỡng coverage tắt** — `v3/vitest.config.ts:44` ghi nguyên văn
"Coverage thresholds disabled for alpha".

Sàng qua bộ lọc "có ích cho dự án này", **còn đúng một thứ**. Ba lý do khiến phần lớn cơ chế của họ rơi:

1. **Ta không có bài toán họ giải.** Swarm topology, consensus, federation nhiều máy đều phục vụ mô hình agent
   tự quyết. Mô hình của repo này là **gate người** (`Studio-creators/docs/adr/0002`, ADR-0037): agent chuẩn bị
   bằng chứng, người ký. Đây là từ chối theo nguyên tắc, không phải vì chưa làm kịp.
2. **Ta đã có, bằng cơ chế khác.** Xem §"Đã kiểm và loại" — hai thứ ban đầu tưởng thiếu hoá ra có sẵn.
3. **Số đo của chính họ không ủng hộ.** Xem HNSW ở §"Đã kiểm và loại".

## Quyết định

### Lấy một: nghi thức tự kiểm chống chính mình

`docs/reviews/intelligence-system-audit-2026-05-29.md` của họ là một bản tự kiểm do sáu auditor chạy đo thật
trên `dist` **đã build**, và nó **bác bỏ chính README của repo mình**. Nguyên văn mở đầu:

> "Headline performance multipliers in `CLAUDE.md` are largely hardcoded doc strings with no benchmark behind
> them; several are unsubstantiated and **one is fabricated at runtime**."

Cụ thể: "HNSW 150x–12.500x" đo được **1,48×**; "Flash Attention 2,49–7,47×" **sinh bằng `Math.random()` lúc
chạy**; "75× embeddings" và "RaBitQ 2,70×" không có benchmark nào. Bản kiểm không chỉ chê — nó xác nhận phần
thật (vòng học 4 bước sống qua hai tiến trình, Int8 **3,92×**, SONA adapt **0,0042 ms**) và tìm ra **một lỗi
đúng-sai**: CLI đảo dấu reward âm — `route feedback -r -1.0` ghi vào **+1,00**, tức người huấn luyện chống một
agent tồi theo đúng cách tài liệu chỉ thì lại **củng cố** nó. Sau bản kiểm, README của họ sửa thành câu có
ngưỡng và có chỗ thua: "~1.9x at N=20k, ~3.2x–4.7x at N=5k … **ties/loses at small N**" (`README.md:204`).

Đây là luật cấm 8 của `AGENTS.md` ("không tin lời khai") được thi hành trên chính mình. Repo này **có luật đó
nhưng chưa có nghi thức bắt nó chạy trên số liệu của chính mình** — `README.md:17-21` đang mang "850 test",
"424 test", "21 agent, 45 skill, 19 topic", "phủ 100% dòng", và không có chỗ nào trong quy trình buộc ai đó
định kỳ đo lại chúng.

**Quyết định:** thêm một mục vào `docs/TASK-PACK.md` — mỗi chân trời một phiên chỉ làm việc đo lại mọi con số
đang nằm trong `README.md`, `ARCHITECTURE.md` và các ADR trạng thái "được chấp nhận", chạy trên gói đã cài chứ
không trên mã nguồn, kết quả là `docs/reports/<ngày>-tu-kiem.md` với ba cột *claim · đo được · chênh*. Số nào
không tái hiện được thì **sửa tài liệu, không sửa phép đo**.

Chọn đúng thứ này vì nó là thứ duy nhất trong cả repo ruflo thoả cả ba: giải một thiếu sót có thật của ta, không
cần một dòng mã mới, và không phụ thuộc bất cứ thứ gì của họ.

### Đã kiểm và loại

Ghi lại **cả chỗ an toàn và vì sao** (`TRAPS.md` §1), gồm hai thứ mà bản nháp đầu của ADR này đã định lấy nhầm.

| Cơ chế của ruflo | Vì sao không lấy |
|---|---|
| Vòng đời bộ nhớ `consolidator.ts` (`sweepExpired`/`dedup` theo content-hash/`compactHnsw`) | **Không map.** Nó dọn một cache quan sát tạm của agent. `blackboard.py` là **event-sourced, đánh version, append-only**: bản ghi đi qua bus (nguồn sự thật, replay dựng lại được, ADR-0012), mirror ra `v<n>.<ext>` + `latest`, `rehydrate()` dựng lại từ bus. Ở đây "hết hạn" và "khử trùng theo hash" **phá** đúng tính chất ta cần — version là chủ đích, không phải rác. `_latest` chỉ giữ một bản mỗi `(project_id, namespace)`, chặn trên bằng số namespace × số dự án; không có rò rỉ để dọn. |
| Agent đọc `docs/SPEC.md` + `docs/adr/*.md` trước khi viết mã, ADR là ràng buộc (`.claude/agents/core/coder.md`) | **Đã có, mạnh hơn.** ADR-0012 bơm **toàn văn** artifact ràng buộc (`prd`, `architecture`, `api-contract`) thẳng vào prompt — agent không phải đi tìm và không thể bỏ sót. Mâu thuẫn thì đã có đường ra riêng (`change-requests`), không phải một câu dặn trong prompt. 17/21 agent đã trích ADR đúng chỗ luật áp dụng. |
| HNSW làm bộ nhớ agent (`hnsw-index.ts`, 1.461 dòng) | Chính bản kiểm của họ đo **1,48×**, và README hiện tại thừa nhận nó **thua ở N nhỏ**. Blackboard ta là N nhỏ theo thiết kế (một bản mỗi namespace mỗi dự án). |
| Consensus giữa agent (`raft.ts`, `byzantine.ts`, `gossip.ts`) | Trái mô hình gate người. Bỏ phiếu giữa các model là thay một người chịu trách nhiệm bằng một đám đông không chịu trách nhiệm. |
| Hook Claude Code kiểu `\|\| true` | `.claude-plugin/hooks/hooks.json` tự khai "**always exits 0** so a CLI/install failure never surfaces an error" — đúng khuôn 1 `TRAPS.md` §1 (lỗi im lặng). Cùng file khai `"_legacy_unaudited_shim": true`, `"_platform": "posix"`, "known-broken on native Windows"; repo này chạy Windows là chính. |
| `import`/phụ thuộc runtime vào `ruflo` | Coverage CI tắt; `package.json` vẫn tên `claude-flow@3.38.21`, homepage vẫn trỏ repo tên cũ — đang giữa một lần đổi tên chưa xong. Đọc để học thì được. |

## Hệ quả

**Được.** Một việc làm được ngay, 0 dòng mã, không chạm `xagents-core` đang xây dở. Sáu lời từ chối có lý do
viết ra, trong đó hai lời là kết quả của việc **đối chiếu ngược lại mã của chính ta** chứ không phải đọc lướt.

**Mất.** Mục tự kiểm tốn một phiên mỗi chân trời, và nó sẽ làm tài liệu **xấu đi trước khi tốt lên** — đúng bản
chất của việc đo.

**Rủi ro đã chặn.** Cám dỗ lớn nhất khi đọc một repo 71k sao là chép cấu trúc của nó ("có swarm topology thì
mình cũng phải có"). Bản nháp đầu của chính ADR này đã sa vào phiên bản nhẹ của cám dỗ đó: định lấy vòng đời bộ
nhớ và mệnh đề ADR-trong-prompt **trước khi** đọc `blackboard.py` và 21 file agent. Đọc rồi thì cả hai rơi. Đó
là `TRAPS.md` §2 (đo trước khi sửa) áp cho việc đọc repo người khác.

**Đã làm trong cùng PR.** Gói việc thường trực ở `docs/TASK-PACK.md`, và **lần tự kiểm đầu tiên đã chạy**:
`docs/reports/2026-09-07-tu-kiem.md` — 5/10 dòng số liệu trong `README.md` gốc lệch với đĩa (850→1001, 424→469,
206→225 test; console ADR 0001–0002→0003; xagents-core thiếu ADR gốc 0003), đều lệch một chiều "nói ít hơn thật",
và đúng những dòng **không có test CI canh**. Đã sửa README. ADR này vẫn **không đổi một dòng mã nào**.

## Liên quan

- `AGENTS.md` luật cấm 8 (không tin lời khai) — cơ sở của việc lấy.
- `companies/software-company/docs/adr/0012-content-context-cost-parallel.md` (toàn văn vào prompt) và `docs/adr/0001-loi-chung-xagents-core.md` — cơ sở
  của hai dòng "đã kiểm và loại" đầu bảng.
- `Studio-creators/docs/adr/0002-approval-first-gates.md` — cơ sở của lời từ chối consensus.
- `TRAPS.md` §1 khuôn 1 (lỗi im lặng) và §2 (đo trước khi sửa).
- Nguồn ngoài: `ruvnet/ruflo` @`277c7bc0` — `docs/reviews/intelligence-system-audit-2026-05-29.md`,
  `README.md:204`, `.claude-plugin/hooks/hooks.json`, `v3/vitest.config.ts:44`,
  `v3/@claude-flow/memory/src/consolidator.ts`, `v3/@claude-flow/swarm/src/consensus/`.
