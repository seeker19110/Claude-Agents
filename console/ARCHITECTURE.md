# ARCHITECTURE.md — console

```
trình duyệt (index.html, một file; PWA cài được; hash route #/<màn>[/gate|ticket|video/<id>])
   │  fetch + SSE /api/stream (đẩy trước, lùi về hỏi lại 10s khi đứt)
   ▼
server.py ── http.server thư viện chuẩn · token phiên mỗi lần chạy · cờ --allow-decide/--allow-submit/--allow-config
   │           không cờ → POST 403; mặc định 127.0.0.1, ra ngoài cần --i-know
   ├── collect.py ── đọc SQLite mode=ro của software-company và Studio-creators: gate, ticket, video, PR, review, audit, chi phí, pool
   ├── truth.py ──── "sự thật giao hàng": phễu release, bế tắc im lặng, quyết định chưa áp, đã giao n/m
   ├── decide.py ─── duyệt gate → HumanGate của công ty (four-eyes, allowlist, audit-log giữ nguyên)
   ├── submit.py ─── việc mới → SQLiteBus của công ty (JSON Schema kiểm như CLI publish)
   └── settings.py ─ đọc/ghi llm.yaml từng công ty (giữ .bak); CLI `models`
```

Sáu màn: trực ban · phần mềm · video · chi phí · nhật ký · cài đặt. Console **hiển thị và publish**, không điều
phối: không có `orchestrator run --watch` của công ty thì mọi thứ nó gửi nằm im trên bus.

Nguyên tắc thiết kế màn hình rút từ vận hành thật (`TRAPS.md`): mỗi con số nói nó đo gì; tách sự thật git khỏi
nhãn FSM; xanh vì rỗng phải cảnh báo; gate hiện `kind` và hậu quả của việc duyệt.
