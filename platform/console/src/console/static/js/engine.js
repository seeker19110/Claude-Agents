/* engine.js — bật/tắt động cơ (`orchestrator run --watch`) của từng xưởng ngay trên trang.

   Câu hỏi ô này trả lời: *công ty có ĐANG CHẠY không, và nếu không thì vì sao?* Trước đó console là mặt kính:
   giao việc xong mà quên bật orchestrator ở terminal thì việc nằm im, không lỗi, không dấu hiệu — chỗ hụt đó
   chính là thứ ô này vá.

   ADR-0003 ("ô rỗng là ô xám"): trạng thái `stopped` KHÔNG BAO GIỜ tô xanh và `exited` tô đỏ kèm mã thoát +
   đuôi log. Một động cơ chết ngay sau khi bấm Bật (thiếu llm.yaml, thiếu API key) nhìn phải khác hẳn một động
   cơ đang chạy, chứ không phải "đã bấm rồi nên chắc là chạy". */
import {CONSOLE, ME_KEY, api} from "./api.js";
import {st} from "./state.js";
import {$, esc} from "./util.js";

export const PILL={running:["good","đang chạy"],stopped:["calm","chưa bật"],exited:["crit","đã dừng"]};
export const DEFAULT_INTERVAL=30;

export const engines=()=>((st().engine||{}).engines)||[];
export const canEngine=()=>!!CONSOLE.can_engine;

export function uptimeTxt(s){
  const n=Math.max(0,Math.round(Number(s||0)));
  if(n<60) return n+" giây";
  if(n<3600) return Math.floor(n/60)+" phút";
  return Math.floor(n/3600)+" giờ "+Math.floor((n%3600)/60)+" phút";
}

export function line(e){
  if(e.state==="running") return `pid ${esc(e.pid)} · nhịp ${esc(e.interval)}s · chạy ${uptimeTxt(e.uptime_s)} · bật bởi ${esc(e.by)}`;
  if(e.state==="exited") return `thoát với mã ${esc(e.exit_code)}${e.stopped_by?` · tắt bởi ${esc(e.stopped_by)}`:" · KHÔNG ai tắt — nó tự chết"}`;
  if(!e.configured) return "console chạy không có đường dẫn bus của xưởng này";
  return "chưa bật lần nào trong phiên console này";
}

export function renderEngine(){
  const box=$("#engine"); if(!box) return;
  const list=engines();
  if(!list.length){ box.innerHTML='<div class="empty"><b>Động cơ</b>chưa đọc được /api/state</div>'; return; }
  const can=canEngine();
  box.innerHTML=(can?"":'<div class="note">Chỉ xem. Bật/tắt được thì chạy lại: <code>python -m console --allow-engine</code></div>')
   +list.map(e=>{
    const [cls,txt]=PILL[e.state]||PILL.stopped;
    const on=e.state==="running";
    const dis=(!can||!e.configured)?" disabled":"";
    return `<div class="eng" data-xuong="${esc(e.xuong)}">
      <div class="eng-head"><b>${esc(e.label)}</b> <span class="pill ${cls}">${esc(txt)}</span></div>
      <div class="note">${line(e)}</div>
      <div class="filters">
        <label class="note">nhịp <input class="eng-interval mono" type="number" min="5" max="3600"
          value="${esc(e.interval||DEFAULT_INTERVAL)}" ${on?"disabled":""}> giây</label>
        <button data-act="${on?"stop":"start"}"${dis}>${on?"Tắt":"Bật"}</button>
        <span class="note" data-note></span>
      </div>
      ${e.tail?`<details><summary class="note">đuôi log (${esc(e.log||"")})</summary><pre class="mono">${esc(e.tail)}</pre></details>`:""}
    </div>`;
  }).join("");
}

/* Một listener ở document thay vì gắn từng nút: `renderEngine` vẽ lại toàn bộ mỗi nhịp, nút cũ biến mất. */
document.addEventListener("click",async e=>{
  const btn=e.target.closest("#engine button[data-act]"); if(!btn) return;
  const row=btn.closest(".eng"), note=$("[data-note]",row);
  const by=localStorage.getItem(ME_KEY)||"human:owner";
  const body={action:btn.dataset.act,xuong:row.dataset.xuong,by};
  if(btn.dataset.act==="start") body.interval=Number($(".eng-interval",row).value)||DEFAULT_INTERVAL;
  btn.disabled=true; note.textContent="đang gửi…";
  try{
    await api("/api/engine",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    note.textContent="";
  }catch(err){
    note.textContent=err.message; btn.disabled=false;
  }
});
