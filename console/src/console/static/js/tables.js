/* tables.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
    */
import {openTicket, openVideo} from "./drawer.js";
import {GW, SC, ST, emptyBox, emptyRow, listOf, srcOk, srcWhy, st} from "./state.js";
import {retry} from "./stream.js";
import {filter} from "./tiles.js";
import {renderReleases} from "./truth.js";
import {$, Q, esc, hay, hl, kb, mmss, num, pctTxt, sortRows} from "./util.js";

/* ---------- bảng & danh sách ---------- */
/* Nhãn là của máy trạng thái delivery-lead, không phải sự thật git: `approved` = review xong, chờ vào release;
   `merged` = release của nó đã lên STAGING; `released` = đã lên production. Gộp vào nhánh tích hợp là dấu riêng. */
export const TSTATE=[["waiting","Chờ phụ thuộc"],["dispatched","Đã giao"],["in_progress","Đang làm"],["in_review","Đang review"],["changes_requested","Trả về sửa"],["approved","Review xong, chờ release"],["merged","Release lên staging"],["released","Lên production"],["closed","Khách đã nghiệm thu"],["blocked","Kẹt"],["escalated","Đã leo thang"]];
export const VSTATE=[["briefed","Đã có đề bài"],["scripted","Đã có kịch bản"],["in_review","Đang review"],["approved","Đã duyệt"],["published","Đã đăng"],["analyzed","Đã phân tích"]];

export function renderBackends(){
  const rows=sortRows("backends",st().backends||[]);
  $("#backends").innerHTML=rows.length?rows.map(b=>`<tr>
    <td class="mono">${esc(b.n)}${b.note?`<div class="note">${esc(b.note)}</div>`:""}</td>
    <td class="mono">${esc(b.tiers)}</td><td>${esc(b.tools)}</td>
    <td><span class="pill ${b.ok?"good":"warn"}">${esc(b.st)}</span></td>
    <td class="mono r">${num(b.calls)}</td><td class="mono r">${num(b.fail)}</td></tr>`).join("")
    :emptyRow(6,GW,"Chưa đọc được gói tài khoản nào");
  const ok=rows.filter(b=>b.ok).length;
  $("#pool-txt").textContent=rows.length?`${ok}/${rows.length} sẵn sàng`:"—";
  $("#pool-bar").style.width=(rows.length?Math.round(ok/rows.length*100):0)+"%";
  const rest=rows.filter(b=>!b.ok);
  $("#pool-note").textContent=rest.length?`${rest[0].n} ${rest[0].st}${rest[0].note?" — "+rest[0].note:""}`
    :rows.length?"tất cả gói đang sẵn sàng":srcWhy(GW);
}
export function board(host,states,items,key,tag,fmt){
  $(host).innerHTML=states.map(([k,label])=>{
    const list=items.filter(x=>x.st===k);
    return `<div class="col"><div class="col-h">${label}<span class="n">${list.length}</span></div>
      ${list.map(x=>{const p=x.bud?Math.min(100,Math.round(x.used/x.bud*100)):0;const cls=p>=100?"over":p>=80?"near":"";
        return `<button class="card" data-${tag}="${esc(x.id)}"><span class="id">${hl(x.id)}</span><span class="t">${hl(x.t)}</span>
          <span class="meter ${cls}"><i style="width:${p}%"></i></span>
          <span class="f">${fmt(x)}</span></button>`;}).join("")
      ||'<div class="note" style="padding:6px 2px">—</div>'}</div>`;}).join("");
}
/* Lọc cột: "all" giữ mọi cột, còn lại thu bảng về đúng một cột — nhìn nhanh một trạng thái mà
   không phải cuộn ngang qua tám cột. */
export const boardFilter={tickets:"all",videos:"all"};
export function chips(host,states,key,items){
  const counts=Object.fromEntries(states.map(([k])=>[k,items.filter(x=>x.st===k).length]));
  $(host).innerHTML=[["all","Tất cả",items.length]].concat(states.map(([k,l])=>[k,l,counts[k]]))
    .map(([k,l,n])=>`<button class="fbtn" data-f="${k}" aria-pressed="${boardFilter[key]===k}">${esc(l)} <b>${n}</b></button>`).join("");
}
export function renderBoards(){
  const tickets=listOf(SC,st().tickets), videos=listOf(ST,st().videos);
  const seen=t=>hay(t.id,t.t,t.who,t.st,t.fmt);
  const cols=(states,key)=>boardFilter[key]==="all"?states:states.filter(([k])=>k===boardFilter[key]);
  chips("#f-tickets",TSTATE,"tickets",tickets);
  chips("#f-videos",VSTATE,"videos",videos);
  if(!srcOk(SC)) $("#board-tickets").innerHTML=emptyBox(SC,"Chưa có dữ liệu xưởng phần mềm");
  else board("#board-tickets",cols(TSTATE,"tickets"),tickets.filter(seen),"st","t",t=>`<span>${esc(t.who)}</span><span title="token đầu ra / ngân sách · tổng token đã tiêu">${kb(t.out)}/${kb(t.bud)} · ${kb(t.used)} tổng</span>${t.retry?`<span>retry ${num(t.retry)}</span>`:""}${t.integrated?'<span class="tag ok">integration ✓</span>':""}${t.gate?`<span class="tag warn">gate ${esc(t.gate)}</span>`:""}${t.pending_decision?'<span class="tag warn">quyết định chưa áp</span>':""}${t.ahead?`<span class="tag warn">${num(t.ahead)} commit chưa gộp</span>`:""}${t.human_hint?'<span class="tag">hint người</span>':""}`);
  if(!srcOk(ST)) $("#board-videos").innerHTML=emptyBox(ST,"Chưa có dữ liệu xưởng video");
  else board("#board-videos",cols(VSTATE,"videos"),videos.filter(seen),"st","vid",v=>`<span>${esc(v.fmt)}</span><span>${kb(v.used)}/${kb(v.bud)}</span>`);
  $("#nav-tickets").textContent=srcOk(SC)?tickets.length:"—";
  $("#nav-videos").textContent=srcOk(ST)?videos.length:"—";
}
[["#f-tickets","tickets"],["#f-videos","videos"]].forEach(([host,key])=>{
  $(host).addEventListener("click",e=>{const b=e.target.closest(".fbtn"); if(!b) return;
    boardFilter[key]=b.dataset.f; renderBoards();});
});
$("#board-tickets").addEventListener("click",e=>{const c=e.target.closest(".card");if(c)openTicket(c.dataset.t);});
$("#board-videos").addEventListener("click",e=>{const c=e.target.closest(".card");if(c)openVideo(c.dataset.vid);});
$("#prs").addEventListener("click",e=>{const r=e.target.closest("tr");if(r&&r.dataset.t)openTicket(r.dataset.t);});

/* C7: `blocked` mang hai nghĩa cho tới khi có con số này — "chưa viết xong" và "viết xong rồi, chưa gộp" cần hai
   hành động ngược nhau. `null` (không đo được) KHÁC 0 (đã gộp hết) và phải hiện khác nhau. */
export function ahead(id){const t=(st().tickets||[]).find(x=>x.id===id); return t?t.ahead:null;}
export function aheadTxt(id){const n=ahead(id); return n==null?'<span class="note">—</span>':n?`<span class="tag warn">${num(n)} commit</span>`:'<span class="tag ok">0</span>';}

export function renderTables(){
  const prs=sortRows("prs",listOf(SC,st().prs).filter(p=>hay(p.id,p.br,p.s,p.v))),
        reviews=sortRows("reviews",listOf(SC,st().reviews).filter(r=>hay(r.id,r.src,r.v,r.f))),
        perf=sortRows("perf",listOf(ST,st().perf).filter(p=>hay(p.id)));
  const okPill=v=>`<span class="pill ${v==="pass"?"good":v==="fail"?"crit":"calm"}">${esc(v)}</span>`;
  $("#prs").innerHTML=prs.length?prs.map(p=>`<tr class="tr-click" data-t="${esc(p.id)}"><td class="mono">${hl(p.id)}</td><td class="mono">${hl(p.br)}</td>
    <td>${hl(p.s)}</td><td>${okPill(p.lint)}</td><td>${okPill(p.tests)}</td><td class="mono">${esc(p.v)}</td>
    <td class="mono r">${aheadTxt(p.id)}</td></tr>`).join("")
    :emptyRow(7,SC,!srcOk(SC)?"Chưa có dữ liệu xưởng phần mềm":Q?"Không có PR nào khớp ô tìm":"Không có PR nào chờ review");
  $("#reviews").innerHTML=reviews.length?reviews.map(r=>`<tr><td class="mono">${hl(r.id)}</td><td class="mono">${esc(r.src)}</td>
    <td><span class="pill ${r.v==="pass"?"good":"crit"}">${esc(r.v)}</span></td><td>${hl(r.f)}</td>
    <td>${(r.trim_src||[]).length?(r.trim_src||[]).map(x=>`<span class="tag warn">${esc(x.src)} −${num(x.chars)} ký tự</span>`).join(" "):'<span class="note">đủ ngữ cảnh</span>'}</td><td class="mono">${esc(r.at||"")}</td></tr>`).join("")
    :emptyRow(6,SC,!srcOk(SC)?"Chưa có dữ liệu xưởng phần mềm":Q?"Không có review nào khớp ô tìm":"Chưa có kết quả review");
  renderReleases();
  $("#perf").innerHTML=perf.length?perf.map(p=>{const w=Math.round(Math.min(1,(p.ctr||0)/.25)*100);
    return `<tr><td class="mono">${hl(p.id)}</td><td class="mono r">${num(p.imp)}</td><td class="mono r">${num(p.views)}</td>
      <td class="mono r">${pctTxt(p.ctr)}</td><td class="mono r">${mmss(p.avd)}</td>
      <td><span class="meter" style="width:88px"><i style="width:${w}%"></i></span></td></tr>`;}).join("")
    :emptyRow(6,ST,!srcOk(ST)?"Chưa có dữ liệu xưởng video":Q?"Không có video nào khớp ô tìm":"Chưa có video nào đăng để đo");
  const sup=sortRows("sup",(st().supervisor||[]).filter(x=>hay(x.t,x.a,x.r)));
  $("#sup").innerHTML=sup.length?sup.map(s=>{const cls=s.a==="warn"?"warn":s.a==="pause"?"calm":"crit";
    return `<tr><td class="mono">${esc(s.t)}</td><td><span class="pill ${cls}">${esc(s.a)}</span></td><td>${esc(s.r)}</td><td class="mono">${esc(s.w)}</td></tr>`;}).join("")
    :emptyRow(4,SC,"Supervisor chưa phải can thiệp lần nào");
  const budg=listOf(SC,st().tickets).filter(t=>t.used>0&&hay(t.id,t.t));
  $("#budgets").innerHTML=budg.length?budg.map(t=>{
    const o=t.out||0, p=t.bud?Math.min(100,o/t.bud*100):0, e=t.bud?Math.min(100,t.est/t.bud*100):0;
    const cls=t.bud&&o>=t.bud?"over":p>=80?"near":"";
    return `<div class="brow"><span class="lbl">${esc(t.id)}</span>
      <span class="track"><i class="${cls}" style="width:${p}%"></i><u style="left:${e}%"></u></span>
      <span class="fig" title="token đầu ra / ngân sách · tổng token">${num(o)} / ${num(t.bud)} · ${kb(t.used)} tổng</span></div>`;}).join("")
    :emptyBox(SC,srcOk(SC)?"Chưa ticket nào tiêu token":"Chưa có dữ liệu xưởng phần mềm");
}
