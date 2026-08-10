import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from src.config import settings

def main():
    print("Bắt đầu nạp dữ liệu Tiêu chuẩn (Ingestion)...")
    data_dir = "data/standards"
    
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Đã tạo thư mục {data_dir}. Vui lòng thêm file vào đây.")
        
    documents = []
    
    # Đọc file txt
    txt_loader = DirectoryLoader(data_dir, glob="**/*.txt", loader_cls=TextLoader, loader_kwargs={'encoding': 'utf-8'})
    documents.extend(txt_loader.load())
    
    # Đọc file pdf
    try:
        pdf_loader = DirectoryLoader(data_dir, glob="**/*.pdf", loader_cls=PyPDFLoader)
        documents.extend(pdf_loader.load())
    except Exception as e:
        print(f"Lưu ý: Bỏ qua đọc PDF do lỗi: {e}")
    
    if not documents:
        print("Không có tài liệu nào trong data/standards/")
        return

    print(f"Đã tải {len(documents)} tài liệu. Bắt đầu chia nhỏ (chunking)...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = text_splitter.split_documents(documents)
    
    print(f"Đã chia thành {len(docs)} chunks. Bắt đầu mã hóa (embedding)...")
    
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "dummy_key_to_prevent_crash_on_import":
        print("LỖI: Chưa cấu hình OPENAI_API_KEY trong .env. Vui lòng thiết lập API KEY trước khi chạy ingest.")
        return
        
    embeddings = OpenAIEmbeddings(api_key=api_key)
    vectorstore = FAISS.from_documents(docs, embeddings)
    
    index_path = "faiss_index"
    vectorstore.save_local(index_path)
    print(f"Nạp thành công! Đã lưu cơ sở dữ liệu Vector (FAISS) tại thư mục '{index_path}'")

if __name__ == "__main__":
    main()
