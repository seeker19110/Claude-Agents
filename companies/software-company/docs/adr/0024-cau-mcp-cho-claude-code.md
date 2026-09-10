# ADR-0024: Cầu MCP cho `claude-code` — giữ nguyên sandbox `tools.py` khi CLI tự chạy vòng tool

## Bối cảnh
ADR-0023 mở khoá "chạy cả công ty bằng gói Claude" bằng **chế độ tool CLI** (`cli_tools`): CLI tự cầm tool của nó
(`Read`/`Edit`/`Write`/`Bash`) trong worktree. Nó chạy được, và ADR đó tự ghi rõ cái giá:

> Hàng rào tool yếu hơn một bậc so với `tools.py` — nó là hệ permission của CLI chứ không phải argv do ta ghép.
> Với repo khách không tin cậy, giữ `cli_tools: false` và đi backend API.

Cụ thể, những thứ ADR-0010 dựng lên không còn áp được: allowlist lệnh (`COMMANDS` theo stack, argv do code ghép,
không có shell), ranh giới đường dẫn `_path`, `_is_secret`, cắt output — thay bằng `--restricted` + deny-list glob
trong `--settings`. Deny-list glob và allowlist argv không cùng một mức đảm bảo. Và vết `ToolBox.calls` biến mất
hẳn: audit `tools_used` rỗng, `Generated.tool_calls` rỗng, `review.no_tool_evidence` bắn nhầm cho mọi lượt QA.

Nghĩa là hôm nay muốn chạy bằng gói Claude thì phải chấp nhận hạ hàng rào — trong khi thứ duy nhất CLI thật sự
thiếu là **kênh trả `tool_calls` ra ngoài**. Nhưng CLI có `--mcp-config`: nó gọi được tool của người khác.

## Quyết định
Chế độ thứ ba, `mcp_tools`, **thắng `cli_tools` khi cùng bật**. CLI vẫn chạy một tiến trình cho cả vòng tool (nên có
prompt cache và tool-use gốc), nhưng tool nó gọi là **đúng bảng tool của công ty**, và chúng thực thi ở tiến trình
cha nơi `ToolBox` thật đang sống:

```
claude -p ──stdio──> python -m company.mcp_bridge ──socket 127.0.0.1──> ToolBox của runner
(MCP client)          (chỉ chuyển tiếp, không logic)                     (allowlist, audit, đếm lượt)
```

- MCP server con **không biết gì** về worktree hay allowlist: nó chỉ chuyển tiếp `tools/list` và `tools/call`. Không
  nhân bản guardrail, không có đường vòng qua nó.
- `ToolBridge` mở socket cổng ngẫu nhiên trên 127.0.0.1, chỉ sống trong lúc gọi CLI, mỗi lời gọi phải mang token dùng
  một phiên (`secrets.token_hex`, so bằng `compare_digest`). File `--mcp-config` mang token nằm trong thư mục tạm và
  bị xoá ngay sau lượt.
- `--strict-mcp-config` + `--allowedTools mcp__company__*`: không kéo MCP server nào của người dùng vào phiên, và
  không mở tool riêng của CLI. Không cần `--restricted`, `--settings` deny-list hay `cli_bash` — vì CLI không có tool
  nào để mà chặn.
- `runner._tool_loop` gọi `client.bind_toolbox(tools)` trước vòng và `bind_toolbox(None)` sau. Đây là phương thức
  **tuỳ chọn** của `ModelClient`; client không có thì mọi thứ chạy y như cũ. `RoutingClient` chuyển tiếp cho mọi
  backend vì chưa biết lượt này sẽ đi backend nào.
- Bật `mcp_tools` mà runner chưa bind (client bị gọi ngoài vòng tool) → **lỗi cứng**, không âm thầm bỏ tool.
- CLI cũ không biết `--mcp-config` → lùi sang `cli_tools` nếu backend có bật, không thì báo lỗi nói đúng việc phải làm.

## Hệ quả
- Chạy cả công ty bằng gói Claude **mà không hạ hàng rào**: allowlist đường dẫn/lệnh, chặn file bí mật, cắt output,
  `tools_used` trong audit và số lần gọi trong metrics giữ nguyên một nguồn sự thật duy nhất là `tools.py`. Test
  `test_real_subprocess_speaks_mcp_and_reaches_the_parent_toolbox` chạy tiến trình MCP thật và chốt rằng `.env` vẫn
  bị chặn, `write_file` ghi thật vào worktree, và `ToolBox` của cha đếm đúng số lần gọi.
- `review.no_tool_evidence` và `Generated.tool_calls` đúng trở lại ở chế độ này (ở `cli_tools` thì không).
- **Đánh đổi giữ nguyên từ ADR-0023**: vòng lặp nằm trong CLI nên `budget` token chỉ kiểm được sau khi CLI trả về;
  trần lượt là `mcp_max_turns`. `Generated.turns` luôn là 1 — số lượt model↔tool nằm ở `tool_calls`.
- Thêm một bề mặt: socket loopback sống vài phút mỗi lần gọi agent có tool. Token một phiên + `127.0.0.1` + đóng ngay
  sau lượt là hàng rào; máy nhiều người dùng chung thì đây là điểm cần biết.
- `cli_tools` không bị bỏ: nó vẫn là đường dự phòng cho CLI cũ, và là cách duy nhất nếu người dùng muốn CLI dùng tool
  riêng của nó. Mặc định cả hai vẫn tắt — hành vi của cấu hình đang chạy không đổi.
- `Studio-creators` chưa dùng cầu này: tool ở đó chỉ đọc web, uỷ quyền thẳng cho CLI (ADR-0007) vẫn hợp lý.
