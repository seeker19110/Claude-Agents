import streamlit as st
from langchain_core.messages import HumanMessage
from src.graph import app as graph_app
import uuid
import os

st.set_page_config(page_title="Văn phòng MEPF Hoàn hảo", layout="wide", page_icon="🏢")

st.title("🏢 Văn phòng Tư vấn Thiết kế MEPF (X-Agents)")
st.markdown("Hệ thống tự động hóa tư vấn chuyên sâu ứng dụng Tiêu chuẩn (RAG), xử lý AutoCAD (DXF), và tự động lập dự toán.")

import pandas as pd

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

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
        with open(f, "rb") as file:
            st.download_button(label=f"⬇️ Tải {f}", data=file, file_name=f)
            
    st.divider()
    st.header("⚙️ Cấu hình hệ thống")
    st.caption("Khởi chạy với Project Manager, MEPF Agents (Tra cứu Tiêu chuẩn), CAD và QS Agents.")
    st.caption("Tính năng bảo mật Human-in-the-loop được tắt trên UI để đảm bảo tự động hóa hoàn toàn.")

tab_chat, tab_excel = st.tabs(["💬 Chat Tư vấn & Bóc tách", "📊 Trình xem Bảng tính Excel"])

with tab_excel:
    st.header("📊 Xem trực tiếp Bảng tính Dự toán Excel")
    excel_files = [f for f in os.listdir('.') if f.endswith('.xlsx') and os.path.isfile(f)]
    if excel_files:
        selected_excel = st.selectbox("📂 Chọn file Excel báo cáo cần xem:", excel_files)
        if selected_excel:
            try:
                df = pd.read_excel(selected_excel)
                st.success(f"Đã nạp file thành công: **{selected_excel}** ({len(df)} dòng dữ liệu)")
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"Lỗi khi đọc file Excel: {e}")
    else:
        st.info("Chưa có file Excel dự toán nào được tạo trong dự án này.")

with tab_chat:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Giao việc cho Giám đốc Dự án (Ví dụ: Thiết kế chiếu sáng phòng khách theo tiêu chuẩn và lập dự toán)...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
        
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        config = {"configurable": {"thread_id": st.session_state.thread_id}}
        
        try:
            for event in graph_app.stream({"messages": [HumanMessage(content=user_input)]}, config=config, stream_mode="updates"):
                for node_name, node_state in event.items():
                    if "messages" in node_state:
                        last_msg = node_state["messages"][-1]
                        name = getattr(last_msg, "name", node_name).upper()
                        content = last_msg.content
                        if not content and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                            tools_used = ", ".join([t['name'] for t in last_msg.tool_calls])
                            content = f"*(Đang sử dụng công cụ: {tools_used}...)*"
                        full_response += f"**[{name}]**\n{content}\n\n---\n"
                        message_placeholder.markdown(full_response + "▌")
            message_placeholder.markdown(full_response)
        except Exception as e:
            full_response += f"\n\n**[LỖI HỆ THỐNG]**\n{str(e)}"
            message_placeholder.markdown(full_response)
            
        st.session_state.chat_history.append({"role": "assistant", "content": full_response})
