# MEP-Agents — Văn phòng Tư vấn Thiết kế MEPF tự động (Multi-Agent)

Hệ thống Multi-Agent mô phỏng một **văn phòng tư vấn thiết kế MEPF** hoàn chỉnh: Giám đốc
Dự án điều phối 7 bộ phận chuyên môn, Kỹ sư trưởng kiểm duyệt đầu ra, và toàn bộ phép tính
kỹ thuật được thực hiện bằng **code Python xác định** thay vì để LLM tự suy đoán con số.

Xây dựng bằng **LangGraph**, giao diện **Streamlit**, theo nguyên tắc
[12-Factor Agents](https://github.com/humanlayer/12-factor-agents).

## Các bộ phận (Agents)

| Bộ phận | Vai trò | Tool tiêu biểu |
|---|---|---|
| **Supervisor** | Giám đốc Dự án — phân việc, điều phối nhiều bước | (định tuyến) |
| **Mechanical** | HVAC: tải lạnh, ống gió, chiller/AHU, thông gió | `calc_cooling_load_detailed`, `calc_duct_total_pressure_loss` |
| **Electrical** | Điện: cáp, aptomat, chiếu sáng, **sụt áp** | `calc_cable_size`, `calc_voltage_drop`, `calc_breaker_size` |
| **Plumbing** | Cấp thoát nước, bể, bơm, nước nóng | `calc_water_pipe`, `calc_plumbing_pump_head` |
| **Firefighting** | PCCC: sprinkler, **bơm chữa cháy (Q và H)**, bình chữa cháy | `calc_fire_pump`, `calc_sprinkler_qty` |
| **QS** | Bóc khối lượng + **lập dự toán có giá trị tiền** | `auto_quantity_takeoff`, `calc_boq_cost`, `lookup_unit_price` |
| **CAD** | Đọc/sửa/tối ưu bản vẽ, phục hồi Block, render ảnh | `edit_cad`, `optimize_cad_drawing`, `ai_block_recovery` |
| **BIM** | Mô hình 3D và **kiểm tra xung đột giữa các hệ** | `detect_clashes`, `auto_quantity_takeoff` |
| **Reviewer** | Kỹ sư trưởng — kiểm duyệt, bắt làm lại nếu chưa đạt | (guardrail) |

## Đặc điểm thiết kế

- 🧮 **Tính toán xác định, không để LLM đoán số**: mọi công thức kỹ thuật nằm trong
  `src/hvac_tools.py`, `elec_tools.py`, `plumb_tools.py`, `ff_tools.py`, `qs_tools.py`,
  `bim_tools.py`. Model AI chỉ chọn tool và diễn giải kết quả.
- 🤖 **Chạy được với model yếu / offline**: các tác vụ nặng (`auto_quantity_takeoff`,
  `optimize_cad_drawing`, `detect_clashes`) gom cả pipeline vào **một lần gọi tool duy
  nhất**, không đòi LLM tự đếm hay tự soạn JSON. `search_standards` có fallback tra cứu
  từ khóa offline khi không có API key. Xem `AI_MODEL_SETUP.md`.
- 🛡️ **Guardrail có hạn mức**: Reviewer kiểm duyệt thật ở **mọi** lần thử; hết
  `MAX_REVIEW_RETRIES` thì dừng và nói rõ "CHƯA ĐẠT" thay vì giả vờ phê duyệt.
- 💾 **Bộ nhớ bền vững**: checkpoint hội thoại ghi xuống SQLite (`CHECKPOINT_DB`), sống
  sót qua restart. Đặt rỗng để quay về RAM.
- 🔒 **Cô lập theo phiên**: mỗi phiên Streamlit có workspace riêng, mọi thao tác file bị
  chặn path traversal (`src/workspace.py`).
- 💰 **Đo token & chi phí thật** theo từng vai trò, lấy từ `usage_metadata` của nhà cung
  cấp (`src/usage.py`) — không phải ước lượng.
- 🎛️ **Mỗi vai trò một model riêng**: `CAD_MODEL_NAME`, `REVIEWER_LLM_PROVIDER`, ... để
  cân đối chất lượng/chi phí. Tool schema cũng được cắt theo vai trò để giảm token.

## Cấu trúc thư mục

```
app.py                  # Giao diện Streamlit (chat, xem Excel, render CAD, bảng token)
main.py                 # Chạy CLI tương tác
src/
  graph.py              # Đồ thị LangGraph + checkpointer + recursion limit
  agents.py             # Supervisor, 7 agent chuyên môn, Reviewer
  state.py              # AgentState và các reducer
  config.py             # Cấu hình tập trung (pydantic-settings)
  tools.py              # Registry tool + tool CAD/file/RAG dùng chung
  hvac_tools.py         # Tính toán HVAC
  elec_tools.py         # Tính toán Điện (kèm kiểm tra sụt áp)
  plumb_tools.py        # Tính toán Cấp thoát nước
  ff_tools.py           # Tính toán PCCC (Q và H bơm chữa cháy)
  qs_tools.py           # Tra đơn giá & lập dự toán BOQ
  bim_tools.py          # Clash detection
  usage.py              # Đo token/chi phí theo vai trò
  workspace.py          # Cô lập workspace theo phiên + chống path traversal
  ingest.py             # Nạp tiêu chuẩn vào FAISS cho RAG
data/
  standards/            # Kho tiêu chuẩn cho RAG (TCVN/ASHRAE...)
  unit_prices.csv       # CSDL đơn giá vật tư/nhân công/máy — SỬA GIÁ Ở ĐÂY
  blocks/               # Thư viện Block MEPF chuẩn
tests/                  # Test suite (pytest)
```

## Cài đặt và chạy

Dự án dùng `uv`.

```bash
# 1. Cấu hình
cp .env.example .env      # rồi điền API key

# 2. (Tùy chọn) Nạp tiêu chuẩn cho RAG — cần OPENAI_API_KEY
uv run python -m src.ingest

# 3. Chạy giao diện web
uv run streamlit run app.py

# Hoặc chạy CLI
uv run main.py

# Chạy test
uv run pytest -q
```

## Lập dự toán (BOQ)

Quy trình đầy đủ từ bản vẽ tới con số tiền:

1. Tải file `.dxf` lên qua sidebar.
2. Giao việc: *"Bóc khối lượng và lập dự toán bản vẽ tang1.dxf"*.
3. QS Agent chạy `auto_quantity_takeoff` → file Excel khối lượng, rồi `calc_boq_cost` →
   file Excel dự toán gồm chi phí trực tiếp, chi phí chung, thu nhập chịu thuế tính
   trước, VAT và tổng giá trị (cấu trúc theo Thông tư 11/2021/TT-BXD).

**Đơn giá nằm ở `data/unit_prices.csv`** — hãy cập nhật theo thời điểm và theo vùng trước
khi dùng cho hồ sơ thật. Hạng mục không tra được đơn giá sẽ được liệt kê kèm cảnh báo
"CHƯA CÓ ĐƠN GIÁ" chứ không bị bỏ qua âm thầm.

## Giám sát bằng LangSmith (Observability)

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxxxx
LANGCHAIN_PROJECT=x_agents_project
```

Toàn bộ "suy nghĩ", thời gian thực thi và lỗi của từng tác nhân sẽ được vẽ trực quan tại
[smith.langchain.com](https://smith.langchain.com/).

## Tài liệu khác

- [`AI_MODEL_SETUP.md`](AI_MODEL_SETUP.md) — chọn model theo vai trò, chế độ offline, chi phí.
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — Docker, docker-compose kèm Ollama, systemd VPS, Streamlit Cloud.
- [`MEPF_BACKLOG.md`](MEPF_BACKLOG.md) — các tính năng còn trong hàng đợi.
- [`Agentic.md`](Agentic.md) — lộ trình phát triển hệ thống Agentic.
