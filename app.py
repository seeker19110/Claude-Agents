import streamlit as st
from langchain_core.messages import HumanMessage
from src.graph import app as graph_app
import uuid
import os
import time
import pandas as pd

st.set_page_config(page_title="Văn phòng MEPF Hoàn hảo", layout="wide", page_icon="🏢")

# 1. Header Trang web (Gọn gàng, Cố định đỉnh)
st.title("🏢 Văn phòng Tư vấn Thiết kế MEPF (X-Agents)")
st.caption("Hệ thống tự động hóa tư vấn chuyên sâu ứng dụng Tiêu chuẩn (RAG), xử lý AutoCAD (DXF), và tự động lập dự toán.")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# 2. Sidebar - Quản lý Hồ sơ
with st.sidebar:
    st.header("📂 Trạm Quản lý Hồ sơ")
    uploaded_file = st.file_uploader("Tải lên bản vẽ (.dxf) hoặc báo cáo (.pdf, .xlsx)...", type=['dxf', 'pdf', 'xlsx'])
    if uploaded_file:
        file_path = os.path.join(os.getcwd(), uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"Đã lưu thành công: {uploaded_file.name}")
        
    st.divider()
    st.header("📥 File Báo cáo (Download)")
    st.info("Sau khi QS hoặc CAD Agent tạo file xong, tải về tại đây.")
    files = [f for f in os.listdir('.') if f.endswith(('.xlsx', '.docx', '.dxf')) and os.path.isfile(f)]
    for f in files:
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            with open(f, "rb") as file:
                st.download_button(label=f"⬇️ {f}", data=file, file_name=f, key=f"dl_{f}")
        with col2:
            if st.button("🗑️", key=f"del_side_{f}", help=f"Xóa file {f}"):
                try:
                    os.remove(f)
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")
            
    st.divider()
    st.header("⚙️ Cấu hình hệ thống")
    st.caption("Khởi chạy với Project Manager, MEPF Agents (Tra cứu Tiêu chuẩn), CAD và QS Agents.")

# 3. Main Area - Tabs
tab_chat, tab_excel = st.tabs(["💬 Chat Tư vấn & Bóc tách", "📊 Trình xem Bảng tính Excel"])

with tab_excel:
    st.header("📊 Xem trực tiếp Bảng tính Dự toán Excel")
    excel_files = [f for f in os.listdir('.') if f.endswith('.xlsx') and os.path.isfile(f)]
    if excel_files:
        col_sel, col_del = st.columns([0.85, 0.15])
        with col_sel:
            selected_excel = st.selectbox("📂 Chọn file Excel báo cáo cần xem:", excel_files)
        with col_del:
            st.write("")
            st.write("")
            if selected_excel and st.button("🗑️ Xóa file", key=f"del_tab_{selected_excel}"):
                try:
                    os.remove(selected_excel)
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")
                    
        if selected_excel and os.path.exists(selected_excel):
            try:
                df = pd.read_excel(selected_excel)
                st.success(f"Đã nạp file thành công: **{selected_excel}** ({len(df)} dòng dữ liệu)")
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"Lỗi khi đọc file Excel: {e}")
    else:
        st.info("Chưa có file Excel dự toán nào được tạo trong dự án này.")

with tab_chat:
    # Render toàn bộ lịch sử tin nhắn
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Thanh Phê duyệt Nhanh (Quick Approval Action Buttons)
    col1, col2, col3 = st.columns([0.22, 0.22, 0.56])
    btn_approve = col1.button("✅ DUYỆT BẢN VẼ", key="btn_approve", use_container_width=True, type="primary")
    btn_reject = col2.button("❌ TỪ CHỐI", key="btn_reject", use_container_width=True)

    chat_input_val = st.chat_input("Giao việc cho Giám đốc Dự án (Ví dụ: Thiết kế chiếu sáng phòng khách theo tiêu chuẩn và lập dự toán)...")

    user_input = None
    if btn_approve:
        user_input = "DUYỆT"
    elif btn_reject:
        user_input = "TỪ CHỐI"
    elif chat_input_val:
        user_input = chat_input_val

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
            
        with st.chat_message("assistant"):
            # Quét các file có sẵn trong hệ thống để tiêm vào Ngữ cảnh cho Agents
            project_files = [f for f in os.listdir('.') if f.endswith(('.dxf', '.pdf', '.xlsx', '.docx')) and os.path.isfile(f)]
            file_context = ""
            if project_files:
                file_context = f"\n\n[THÔNG TIN HỆ THỐNG: Danh sách các file hồ sơ/bản vẽ ĐANG CÓ SẴN trong dự án gồm: {project_files}. Hãy chọn file phù hợp nhất từ danh sách này nếu người dùng không chỉ định tên file cụ thể]."
                
            full_user_prompt = user_input + file_context
            
            message_placeholder = st.empty()
            full_response = ""
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            start_time = time.time()
            
            with st.status("🚀 Giám đốc Dự án đang điều phối nhân sự xử lý...", expanded=True) as status_container:
                try:
                    for event in graph_app.stream({"messages": [HumanMessage(content=full_user_prompt)]}, config=config, stream_mode="updates"):
                        for node_name, node_state in event.items():
                            if "messages" in node_state:
                                last_msg = node_state["messages"][-1]
                                name = getattr(last_msg, "name", node_name).upper()
                                content = last_msg.content
                                is_tool_status = False
                                
                                if not content and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                                    tools_used = ", ".join([t['name'] for t in last_msg.tool_calls])
                                    content = f"*(⏳ Đang thực thi công cụ: `{tools_used}`...)*"
                                    is_tool_status = True
                                    status_container.update(label=f"⚙️ **{name}** đang chạy công cụ: `{tools_used}`...", state="running")
                                else:
                                    status_container.update(label=f"🧠 **{name}** đang phân tích và lập báo cáo...", state="running")
                                
                                badge_title = f"### 🏢 [{name}]\n"
                                full_response += f"{badge_title}{content}\n\n---\n"
                                
                                elapsed = max(time.time() - start_time, 0.01)
                                est_tokens = max(1, int(len(full_response) / 4))
                                tps = est_tokens / elapsed
                                
                                if is_tool_status:
                                    live_speed = f"*(⏳ Đang xử lý dữ liệu... | Thời gian: {elapsed:.1f}s)*"
                                else:
                                    live_speed = f"*(⚡ Tốc độ sinh AI: **{tps:.1f} tokens/s** | Thời gian: {elapsed:.1f}s)*"
                                
                                message_placeholder.markdown(full_response + "\n" + live_speed + " ▌")
                                
                    elapsed = max(time.time() - start_time, 0.01)
                    est_tokens = max(1, int(len(full_response) / 4))
                    tps = est_tokens / elapsed
                    speed_summary = f"\n*(⚡ Tốc độ sinh: **{tps:.1f} tokens/giây** | Thời gian xử lý: **{elapsed:.2f}s** | Dung lượng: **~{est_tokens} tokens**)*\n"
                    full_response += speed_summary
                    message_placeholder.markdown(full_response)
                    status_container.update(label="✅ Đã hoàn tất nhiệm vụ!", state="complete", expanded=False)
                except Exception as e:
                    full_response += f"\n\n**[LỖI HỆ THỐNG]**\n{str(e)}"
                    message_placeholder.markdown(full_response)
                    status_container.update(label="❌ Gặp lỗi hệ thống!", state="error")
                
            st.session_state.chat_history.append({"role": "assistant", "content": full_response})
