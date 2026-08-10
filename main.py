from langchain_core.messages import HumanMessage
from src.graph import app

def run_multi_agent():
    print("=== Khởi chạy Multi-Agent System (Unified & Optimized) ===")
    
    config = {"configurable": {"thread_id": "test_user_1"}, "recursion_limit": 10}
    
    print("\n--- Test 1: Tìm kiếm tài liệu ---")
    initial_state_1 = {"messages": [HumanMessage(content="Tôi cần tìm kiếm tài liệu về chính sách bảo mật.")]}
    for s in app.stream(initial_state_1, config=config):
        if "__end__" not in s:
            print(s)
            
    print("\n--- Test 2: Ghi nhớ hội thoại ---")
    initial_state_2 = {"messages": [HumanMessage(content="Hãy tóm tắt lại nội dung bạn vừa tìm được.")]}
    for s in app.stream(initial_state_2, config=config):
        if "__end__" not in s:
            print(s)

    print("\n--- Test 3: Vòng lặp sửa lỗi (Retry Loop) ---")
    initial_state_3 = {"messages": [HumanMessage(content="Hãy thực hiện hành động giả lập thử lỗi.")], "errors": []}
    for s in app.stream(initial_state_3, config={"configurable": {"thread_id": "test_user_error_3"}, "recursion_limit": 10}):
        if "__end__" not in s:
            print(s)

if __name__ == "__main__":
    run_multi_agent()
