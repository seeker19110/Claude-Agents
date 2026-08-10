from langchain_core.tools import tool

@tool
def search_web(query: str) -> str:
    """Tìm kiếm thông tin trên internet."""
    print(f"\n[Tool Execution] Searching web for: {query}")
    # Giả lập kết quả tìm kiếm thực tế thay vì gọi API search thực sự để tiết kiệm
    return f"Kết quả tìm kiếm cho '{query}': Công ty X vừa ra mắt sản phẩm Y với nhiều tính năng ưu việt, dự báo doanh thu tăng 20% trong quý tới."

@tool
def calculate(expression: str) -> str:
    """Thực hiện các phép tính toán học cơ bản. Đầu vào là biểu thức toán học dạng chuỗi, ví dụ: '25 * 4 + 10'."""
    print(f"\n[Tool Execution] Calculating: {expression}")
    try:
        # Sử dụng eval một cách an toàn (chỉ tính toán cơ bản) - TRONG THỰC TẾ NÊN DÙNG AST HOẶC THƯ VIỆN TOÁN HỌC
        result = eval(expression, {"__builtins__": {}})
        return f"Kết quả của phép tính '{expression}' là: {result}"
    except Exception as e:
        return f"Lỗi khi tính toán: {e}"

# Danh sách các tool để truyền cho ToolNode và LLM
tools = [search_web, calculate]
