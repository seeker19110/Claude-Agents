/* api.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
    */
/* ---------- cầu nối với server cục bộ ---------- */
export const CONSOLE=window.__CONSOLE__||{};
export const TOKEN=CONSOLE.token||"";
export const READONLY=CONSOLE.readonly!==false;          // không biết thì coi như chỉ đọc
export const ME_KEY="x-agents-console-by";
export const HTTP={400:"Tham số không hợp lệ.",401:"Token phiên không đúng — mở lại trang từ địa chỉ server in ra.",
  403:"Bị chặn (chế độ chỉ đọc hoặc Origin lạ).",404:"Không có đường dẫn này.",409:"Gate đã được quyết rồi.",
  500:"Server gặp lỗi không lường trước."};
export const httpMsg=s=>HTTP[s]||("Server trả HTTP "+s+".");

export async function api(path,init){
  const r=await fetch(path,Object.assign({cache:"no-store"},init,
    {headers:Object.assign({"X-Console-Token":TOKEN},(init&&init.headers)||{})}));
  let body=null; try{body=await r.json();}catch(_){}
  if(!r.ok) throw new Error((body&&body.error)||httpMsg(r.status));
  return body;
}
