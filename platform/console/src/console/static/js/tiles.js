/* tiles.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
    */
import {S, SC, emptyBox, srcOk, srcWhy, st} from "./state.js";
import {stream} from "./stream.js";
import {$, $$, dec2, esc, hay, hl, kb, num, vnd} from "./util.js";

/* ---------- ô số ---------- */
export function renderTiles(){
  const t=st().tiles||{}, any=srcOk(SC);
  const v=(id,val)=>{$(id).textContent=any&&val!=null?val:"—";};
  v("#t-events",num(t.events)); $("#t-events-n").textContent=any?`${num(t.queue)} chưa xử lý (không tính audit)`:srcWhy(SC);
  v("#t-calls",num(t.model_calls)); $("#t-calls-n").textContent=any?`${num(t.tool_calls)} lời gọi tool`:"—";
  v("#t-tok",kb(t.tokens)); $("#t-tok-n").textContent=any?`trần dự án ${kb(t.project_budget_tokens)}`:"—";
  v("#t-rework",dec2(t.rework_rate)); $("#t-rework-n").textContent=any?`review bắt ${dec2(t.review_catch_rate)}`:"—";
  v("#t-prs",num(t.prs_unverified));

  $("#chip-cost").innerHTML=any?`${vnd(t.cost_today_usd)} <span style="font-size:11px;font-weight:400">USD</span>`:"—";
  $("#chip-tokens").textContent=any?kb(t.tokens_today):"—";
  $("#chip-stuck").textContent=any?num(t.stuck_tickets):"—";

  const spent=Number(t.project_cost_usd||0), cap=Number(t.project_budget_usd||0);
  const series=(st().cost_days||{}).series||[];
  const recent=series.slice(-7).map(d=>d.reduce((a,b)=>a+b,0));
  const rate=recent.length?recent.reduce((a,b)=>a+b,0)/recent.length:0;
  v("#c-spent",vnd(spent)); $("#c-spent-n").textContent=any?`trần ${vnd(cap)} USD`:"—";
  v("#c-left",vnd(Math.max(0,cap-spent)));
  $("#c-left-n").textContent=!any?"—":rate>0?`theo nhịp hiện tại: ${Math.floor(Math.max(0,cap-spent)/rate)} ngày`:"chưa đủ dữ liệu để ước nhịp";
  v("#c-unpriced",num(t.unpriced_calls));
  v("#c-cal",dec2(t.calibration));
}

/* ---------- nhật ký ---------- */
export let filter="all";
export const FILTERS=[["all","Tất cả"],["produced","Sản phẩm agent"],["gate","Gate"],["supervisor","Supervisor"],["human","Người"],["error","Lỗi & chặn"]];
export const matchFilter=e=>filter==="all"||
  (filter==="produced"&&String(e.ac).startsWith("produced:"))||
  (filter==="gate"&&String(e.ac).startsWith("gate."))||
  (filter==="supervisor"&&["budget_cut","pause","warn","resume","escalate"].includes(e.ac))||
  (filter==="human"&&String(e.a).startsWith("human:"))||
  (filter==="error"&&["llm_error","publish_denied","injection_sanitized","tick_error","invalid_output"].includes(e.ac));
export const matches=e=>matchFilter(e)&&hay(e.a,e.ac,e.k,e.t);
export function evRow(e){
  const bad=["llm_error","publish_denied","tick_error","invalid_output","budget_cut"].includes(e.ac);
  const soft=["injection_sanitized","warn","pause","review.reassign"].includes(e.ac);
  return `<div class="ev"><span class="t">${esc(e.t)}</span><span class="a">${hl(e.a)}</span>
    <span><code style="${bad?"color:var(--crit-ink)":soft?"color:var(--warn-ink)":""}">${esc(e.ac)}</code> <span style="color:var(--ink-muted)">${esc(e.k)}</span></span>
    <span class="tok">${e.tok?kb(e.tok)+" tok":"—"}${e.c?" · "+vnd(e.c)+" $":""}</span></div>`;
}
export function renderStreams(){
  const log=st().log||[];
  $("#stream-mini").innerHTML=log.length?log.slice(0,10).map(evRow).join("")
    :emptyBox(SC,"Chưa có bản ghi audit nào");
  const rows=log.filter(matches);
  $("#stream-full").innerHTML=rows.length?rows.map(evRow).join("")
    :log.length?'<div class="empty">Không có bản ghi nào khớp bộ lọc này.</div>'
    :emptyBox(SC,"Chưa có bản ghi audit nào");
}
$("#filters").innerHTML=FILTERS.map(f=>`<button class="fbtn" data-f="${f[0]}" aria-pressed="${f[0]==="all"}">${f[1]}</button>`).join("");
$("#filters").addEventListener("click",e=>{const b=e.target.closest(".fbtn");if(!b)return;
  // Chỉ đụng chip trong chính khối này: bảng ticket và video cũng dùng .fbtn.
  filter=b.dataset.f;$$(".fbtn",$("#filters")).forEach(x=>x.setAttribute("aria-pressed",String(x===b)));renderStreams();});
