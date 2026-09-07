# ARCHITECTURE.md — software-company

Bản đồ đầy đủ: [`docs/architecture.md`](docs/architecture.md) (nguyên tắc, bảng topic producer/consumer được test đối
chiếu với `ROUTES`, vòng đời ticket, trạng thái, human gate). Tiêu chuẩn ngành từng khối: `docs/standards.md`. Quyết
định: `docs/adr/` 0001–0029. File này chỉ là lối vào nhanh.

## Một ticket đi qua đâu

```
yêu cầu thô ─► intake ─► researcher (4 mảng) ─► synthesizer ─► risk ─► clarifier ⇄ người ─► spec-writer
   ─► GATE spec ─► security (threat model) ─► delivery-lead (plan, ticket) ─► GATE plan
   ─► [test-author lượt mù] ─► engineering (worktree ticket/<id>, lint/test thật) ─► reviewer + qa-debugger (+ security nếu risk_tags)
   ─► delivery-lead: approved → merge vào company/integration ─► release-candidate
   ─► release-engineer staging ─► ORCHESTRATOR SMOKE (ADR-0029) ─► qa-debugger hồi quy ─► GATE release
   ─► release-engineer production ─► tag v<version> + company/release (ADR-0027) ─► GATE acceptance (khách ký)
```

Kẹt ở đâu cũng có đường ra: agent tự dừng / smoke fail / retry hết → gate `escalation`; supervisor đếm ngân sách và
bế tắc. Không đường nào được kết thúc trong im lặng (`../TRAPS.md` §1).

## Lớp code (`src/company/`)

| Lớp | Module | Vai trò |
|---|---|---|
| Hợp đồng | `events.py`, `topics/schemas/`, `registry.py` | topic, payload Pydantic, agent đọc/ghi gì |
| Bus | `bus.py`, `sqlite_bus.py`, `blackboard.py` | publish có kiểm producer + schema; replay; artifact theo namespace |
| Điều phối | `orchestrator.py`, `delivery.py`, `gates.py`, `gate_cli.py`, `supervisor.py` | route, máy trạng thái ticket/release, human gate bền, watchdog |
| Chạy agent | `runner.py`, `tools.py`, `guard.py`, `context.py`, `subagents.py` | vòng lặp tool, ranh giới tin cậy, injection, hạn mức ngữ cảnh |
| Bằng chứng | `workspace.py`, `stacks.py`, `smoke.py` | worktree, lint/test thật, merge/deliver, smoke |
| Model | `llm.py`, `routing.py`, `mcp_bridge.py`, `probe.py`, `web.py` | adapter, tier, xoay quota, cầu MCP |
| Quan sát | `metrics.py`, `evals.py`, `assetscan.py`, `gate_brief.py`, `gate_checklists.py` | số liệu, eval ghi/phát lại, quét prompt, hồ sơ gate |

## Ranh giới tin cậy — thứ giữ cho hệ không tự lừa mình

Model **chỉ trả JSON**; mọi hành động có hậu quả là code: ghi file trong worktree qua `tools.py` (allowlist, khoá
đường dẫn, env đã lọc, không hook git), lint/test qua `stacks.py`, merge/tag/push qua `workspace.py`, smoke qua
`smoke.py`. Trường "đã làm được" do code điền (`verified_by=workspace|orchestrator`); identity của event do ROUTE
quyết. Chi tiết: ADR-0010, 0013, 0027, 0028, 0029.
