/* util.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
   "use strict" không cần: mọi ES module đã ở chế độ strict. */
import {render} from "./main.js";

export const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
export const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
export const vnd=n=>Number(n||0).toLocaleString("vi-VN",{minimumFractionDigits:2,maximumFractionDigits:2});
export const num=n=>Number(n||0).toLocaleString("vi-VN");
export const kb=n=>n>=1000?(n/1000).toLocaleString("vi-VN",{maximumFractionDigits:1})+"k":String(n||0);
export const pctTxt=n=>(Number(n||0)*100).toFixed(1).replace(".",",")+"%";
export const dec2=n=>Number(n||0).toLocaleString("vi-VN",{minimumFractionDigits:2,maximumFractionDigits:2});
export const mmss=s=>Math.floor(s/60)+":"+String(Math.round(s%60)).padStart(2,"0");

/* ---------- tìm kiếm ----------
   Gấp dấu tiếng Việt để gõ "ke hoach" cũng ra "kế hoạch". Tách dấu bằng NFD rồi bỏ dải
   ký tự tổ hợp U+0300–U+036F — cách này không cần bảng tra và đúng cho cả chữ hoa. */
export const COMB=new RegExp("["+String.fromCharCode(0x300)+"-"+String.fromCharCode(0x36f)+"]","g");
export const fold=v=>String(v??"").normalize("NFD").replace(COMB,"").toLowerCase();
export let Q="";                                         // đã gấp dấu — dùng để LỌC
export let QRAW="";                                      // nguyên văn, chỉ hạ chữ hoa — dùng để TÔ
export const hay=(...fields)=>!Q||fields.some(f=>fold(f).includes(Q));
/* Tô chỗ khớp bằng chuỗi nguyên văn chứ không phải chuỗi đã gấp dấu: NFD tách dấu thành ký tự
   riêng nên chỉ số ký tự lệch, cắt theo đó sẽ tô trượt. Hệ quả: gõ có dấu thì thấy vệt vàng,
   gõ không dấu vẫn lọc đúng nhưng không tô — hỏng nhẹ, không sai. */
export function hl(text){
  const raw=String(text??"");
  if(!QRAW) return esc(raw);
  const i=raw.toLowerCase().indexOf(QRAW);
  if(i<0) return esc(raw);
  return esc(raw.slice(0,i))+"<mark>"+esc(raw.slice(i,i+QRAW.length))+"</mark>"+esc(raw.slice(i+QRAW.length));
}

/* ---------- sắp xếp bảng ---------- */
export const SORT={};                                  // id bảng -> {k, dir}
export function sortRows(table,rows){
  const s=SORT[table]; if(!s) return rows;
  const numeric=s.t==="n";
  return rows.slice().sort((a,b)=>{
    const x=a[s.k], y=b[s.k];
    const c=numeric?Number(x||0)-Number(y||0):fold(x).localeCompare(fold(y),"vi");
    return s.dir==="desc"?-c:c;
  });
}
document.addEventListener("click",e=>{
  const th=e.target.closest("thead th[data-k]"); if(!th) return;
  const head=th.closest("tr[data-sort]"); if(!head) return;
  const table=head.dataset.sort, k=th.dataset.k, cur=SORT[table];
  SORT[table]=cur&&cur.k===k&&cur.dir==="asc"?{k,t:th.dataset.t,dir:"desc"}:{k,t:th.dataset.t,dir:"asc"};
  [...head.children].forEach(c=>c.removeAttribute("aria-sort"));
  th.setAttribute("aria-sort",SORT[table].dir==="asc"?"ascending":"descending");
  render();
});

/* Q/QRAW bị `main` (ô tìm) gán lại. ESM: binding nhập về là CHỈ ĐỌC, nên đổi qua setter —
   đây là khác biệt DUY NHẤT giữa scope chung cũ và module (K7.1). */
export function setQ(q, raw){ Q=q; QRAW=raw; }
