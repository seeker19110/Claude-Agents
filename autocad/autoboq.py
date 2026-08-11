import json
import urllib.request
import win32com.client
import sys

API_URL = "http://localhost:8083/api/v1/autocad/analyze"

def get_acad_elements():
    try:
        acad = win32com.client.Dispatch("AutoCAD.Application")
        doc = acad.ActiveDocument
        model_space = doc.ModelSpace
        
        elements_data = []
        
        # Quét các đối tượng trong ModelSpace
        # Để không bị chậm, chỉ lấy 1000 đối tượng đầu tiên làm demo
        count = 0
        for entity in model_space:
            if count > 1000:
                break
                
            el_dict = {
                "id": entity.ObjectID,
                "layer": entity.Layer,
                "type": entity.ObjectName
            }
            
            # Nếu là đường thẳng/Pline, lấy độ dài
            if entity.ObjectName in ["AcDbLine", "AcDbPolyline"]:
                try:
                    el_dict["length"] = entity.Length
                except:
                    pass
                    
            elements_data.append(el_dict)
            count += 1
            
        return {"project_name": doc.Name, "elements": elements_data}
        
    except Exception as e:
        print("Lỗi khi kết nối AutoCAD:", str(e))
        return None

def main():
    print("Đang quét mô hình AutoCAD hiện tại...")
    payload_dict = get_acad_elements()
    
    if not payload_dict:
        print("Không thể lấy dữ liệu từ AutoCAD. Hãy chắc chắn AutoCAD đang mở.")
        return
        
    print(f"Đã trích xuất {len(payload_dict['elements'])} cấu kiện. Đang gửi lên API...")
    
    payload = json.dumps(payload_dict).encode('utf-8')
    
    req = urllib.request.Request(API_URL, data=payload, headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))
        print("\n=== KẾT QUẢ TỪ SWARM AI ===")
        print(result.get("message", ""))
    except Exception as e:
        print("Lỗi API FastAPI:", str(e))
        
    input("\nNhấn Enter để thoát...")

if __name__ == "__main__":
    main()
