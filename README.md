# X-Agents (Multi-Agent System)

Dự án này là một hệ thống Multi-Agent được tối ưu hóa dựa trên các nguyên tắc của [12-Factor Agents](https://github.com/humanlayer/12-factor-agents).

Hệ thống được thiết kế bằng **LangGraph** (Python) với các đặc điểm:
- 🧠 **Supervisor Routing**: Có một nhạc trưởng điều phối các tác nhân con.
- 💾 **Persistence (MemorySaver)**: Ghi nhớ hội thoại theo `thread_id`.
- 🛡️ **Reviewer Guardrail**: Tác nhân kiểm duyệt đánh giá kết quả trước khi trả về cho người dùng.
- 📦 **Stateful**: Quản lý State bằng biến `context` (dữ liệu dùng chung) và `errors` (xử lý lỗi).

## Cấu trúc thư mục

- `main.py`: File chạy chính.
- `src/state.py`: Định nghĩa lược đồ dữ liệu chung cho đồ thị.
- `src/agents.py`: Chứa mã nguồn của toàn bộ các tác nhân (Supervisor, RAG, Tool, Reviewer).
- `src/graph.py`: Định nghĩa các node, edge và kết nối Đồ thị LangGraph.
- `agentic.md`: Lộ trình phát triển hệ thống Agentic Vibe Coding.

## Cài đặt và Chạy

Dự án sử dụng `uv` để quản lý môi trường và thư viện.

```bash
# Chạy dự án
uv run main.py
```
