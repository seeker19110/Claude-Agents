import sys
from langchain_core.messages import HumanMessage
from src.graph import app
from src.config import settings

def print_stream(stream):
    for s in stream:
        if "__end__" not in s:
            # Lấy tên node vừa chạy
            node_name = list(s.keys())[0]
            print(f"\n--- {node_name.upper()} ---")
            
            # Xử lý các loại tin nhắn hoặc trạng thái
            state = s[node_name]
            
            # Nếu node là tools, nó trả về thông tin tool
            if node_name == "tools":
                if "messages" in state and len(state["messages"]) > 0:
                    last_msg = state["messages"][-1]
                    print(f"Tool Result: {last_msg.content}")
                continue
                
            # Xử lý tin nhắn
            if "messages" in state and len(state["messages"]) > 0:
                last_msg = state["messages"][-1]
                # Kiểm tra xem có tool calls không
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    print(f"Tác nhân đang muốn gọi công cụ: {last_msg.tool_calls[0]['name']}")
                else:
                    print(f"Output: {last_msg.content}")
            
            # Xử lý next agent (từ supervisor)
            if "next" in state:
                print(f"Điều hướng tới: {state['next']}")
                
            # Xử lý lỗi (từ reviewer)
            if "errors" in state and len(state["errors"]) > 0:
                print(f"CẢNH BÁO / LỖI: {state['errors'][-1]}")

def interactive_loop():
    print(f"=== Khởi chạy Multi-Agent System (Unified & Optimized) ===")
    print(f"Mô hình đang sử dụng: {settings.model_name}")
    print("Gõ 'quit' hoặc 'exit' để thoát.")
    
    config = {"configurable": {"thread_id": "interactive_user_1"}, "recursion_limit": 20}
    
    while True:
        try:
            user_input = input("\n[User]: ")
            if user_input.lower() in ["quit", "exit"]:
                print("Đóng hệ thống...")
                break
            if not user_input.strip():
                continue
            
            initial_state = {"messages": [HumanMessage(content=user_input)]}
            
            # Chạy graph cho đến khi xong hoặc bị interrupt
            stream = app.stream(initial_state, config=config, stream_mode="updates")
            print_stream(stream)
            
            # Kiểm tra xem có bị ngắt (interrupt) không
            state = app.get_state(config)
            if state.next: # Có node tiếp theo nhưng graph đã dừng => bị interrupt
                print("\n[HỆ THỐNG] Tác nhân chuẩn bị thực thi công cụ (Tool).")
                print("Nhấn 'y' để cho phép, hoặc 'n' để từ chối.")
                approval = input("Phê duyệt? (y/n): ")
                
                if approval.lower() == 'y':
                    print("\n[HỆ THỐNG] Đã phê duyệt. Tiếp tục thực thi...")
                    # Tiếp tục graph bằng cách truyền None (không thay đổi state)
                    stream = app.stream(None, config=config, stream_mode="updates")
                    print_stream(stream)
                else:
                    print("\n[HỆ THỐNG] Đã hủy thực thi công cụ.")
                    # Chúng ta có thể reset state hoặc thêm tin nhắn người dùng hủy
                    # Để đơn giản trong demo này, chúng ta sẽ bắt đầu lại luồng hoặc mặc kệ.
                    
        except KeyboardInterrupt:
            print("\nĐóng hệ thống...")
            break
        except Exception as e:
            print(f"\nĐã có lỗi xảy ra: {e}")

if __name__ == "__main__":
    if not settings.openai_api_key:
        print("LỖI: Chưa cấu hình OPENAI_API_KEY trong file .env")
        sys.exit(1)
        
    interactive_loop()
