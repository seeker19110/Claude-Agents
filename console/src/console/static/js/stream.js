/* stream.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
    */
import {TOKEN, api, httpMsg} from "./api.js";
import {render} from "./main.js";
import {applyRoute} from "./router.js";
import {S, banner, drawerOpen, firstLoad, lastOk, paused, setFirstLoad, setLastOk, setPaused, setS, setTimer, timer} from "./state.js";
import {$} from "./util.js";

/* ---------- vòng đọc ---------- */
export function skeleton(){
  document.body.classList.add("loading");
  $("#queue").innerHTML='<div class="skel skel-row"></div><div class="skel skel-row"></div><div class="skel skel-row"></div>';
  $("#stream-mini").innerHTML=Array.from({length:6},()=>'<div class="skel skel-line" style="margin:9px 14px"></div>').join("");
  $("#stream-full").innerHTML=$("#stream-mini").innerHTML;
  $("#backends").innerHTML='<tr><td colspan="6"><div class="skel skel-line"></div></td></tr>';
  $("#fresh").textContent="đang đọc…";
}
/* Trạng thái mới về trong lúc người dùng đang đọc (ngăn kéo mở, hoặc đã bấm Tạm dừng) thì
   giữ lại chứ không vẽ đè dưới tay họ — và báo có gì đó mới để họ tự bấm xem. */
export let pending=null;

export let routed=false;
export function accept(data){
  setS(data); pending=null; setLastOk(new Date()); banner(null);
  setFirstLoad(false); document.body.classList.remove("loading"); render();
  // Ngăn kéo trong địa chỉ chỉ mở được sau khung dữ liệu đầu tiên: trước đó chưa có gate nào để tìm.
  if(!routed){ routed=true; applyRoute(); }
}
export function offer(data){
  if(paused||drawerOpen){ pending=data; freshLabel(); return; }
  accept(data);
}
export function applyPending(){ if(pending) accept(pending); else freshLabel(); }

export function lostContact(err){
  banner(S?"Mất liên lạc với server console — số liệu dưới đây là lần đọc cuối.":"Chưa đọc được trạng thái.",
    err.message+(lastOk?" · lần đọc cuối "+lastOk.toLocaleTimeString("vi-VN"):""));
  setFirstLoad(false); document.body.classList.remove("loading"); render();
}

/* ---------- vòng đọc: đẩy trước, hỏi sau ----------
   Ưu tiên `/api/stream` (SSE) để gate mới hiện ngay thay vì chờ hết nhịp 10 giây. Đọc bằng
   `fetch` + ReadableStream chứ không phải `EventSource`: `EventSource` không đặt được header,
   mà token phiên chỉ được đi ở `X-Console-Token` — nhét vào query string là ghi token ra log
   server. Stream đứt thì tự lùi về hỏi lại 10 giây một lần, nên mất SSE chỉ là chậm hơn. */
export const POLL_MS=10000;
export let mode="off", ctrl=null, retry=null, backoff=1000;

export async function load(){
  try{ offer(await api("/api/state")); }
  catch(err){ lostContact(err); }
}

export function parseFrame(chunk){
  let event="message", data="";
  for(const line of chunk.split("\n")){
    if(line.startsWith("event:")) event=line.slice(6).trim();
    else if(line.startsWith("data:")) data+=line.slice(5).trim();
  }
  if(!data) return null;                          // ": ping" — nhịp tim, không phải khung dữ liệu
  try{ return {event,data:JSON.parse(data)}; }catch(_){ return null; }
}

export async function stream(){
  ctrl=new AbortController();
  const r=await fetch("/api/stream",{cache:"no-store",signal:ctrl.signal,
    headers:{"X-Console-Token":TOKEN,"Accept":"text/event-stream"}});
  if(!r.ok||!r.body) throw new Error(httpMsg(r.status));
  setMode("live"); backoff=1000; clearTimeout(timer);
  const reader=r.body.getReader(), dec=new TextDecoder();
  let buf="";
  for(;;){
    const {value,done}=await reader.read();
    if(done) break;
    buf+=dec.decode(value,{stream:true});
    let i;
    while((i=buf.indexOf("\n\n"))>=0){
      const frame=parseFrame(buf.slice(0,i)); buf=buf.slice(i+2);
      if(!frame) continue;
      if(frame.event==="error") banner("Server đọc được stream nhưng không đọc được bus.",frame.data.error||"");
      else offer(frame.data);
    }
  }
  throw new Error("stream đóng");
}

export function poll(){
  clearTimeout(timer);
  if(paused) return;
  setTimer(setTimeout(async()=>{ await load(); poll(); },POLL_MS));
}

export function setMode(m){ mode=m; freshLabel(); }

export async function connect(){
  if(paused) return;
  clearTimeout(retry);
  try{ await stream(); }
  catch(err){
    if(err.name==="AbortError") return;            // chính mình huỷ khi bấm Tạm dừng
    setMode("poll"); load(); poll();               // vẫn chạy được, chỉ chậm hơn
    backoff=Math.min(backoff*2,60000);
    retry=setTimeout(connect,backoff);             // thử lại stream, không quấy server
    return;
  }
  setMode("poll"); poll();
  retry=setTimeout(connect,backoff);
}

export function stop(){ clearTimeout(timer); clearTimeout(retry); if(ctrl) ctrl.abort(); ctrl=null; setMode("off"); }

$("#pause").addEventListener("click",()=>{
  setPaused(!paused);
  $("#pause").setAttribute("aria-pressed",String(paused));
  $("#pause").textContent=paused?"Tiếp tục":"Tạm dừng";
  if(paused) stop(); else { applyPending(); backoff=1000; connect(); }
  freshLabel();
});

export function freshLabel(){
  const f=$("#fresh"), live=$("#live");
  live.className=mode==="live"?"on":mode==="poll"?"poll":"off";
  live.textContent=mode==="live"?"trực tiếp":mode==="poll"?"hỏi lại 10s":"đã dừng";
  if(firstLoad){f.textContent="đang đọc…";return;}
  const t=lastOk?lastOk.toLocaleTimeString("vi-VN"):"chưa có";
  if(pending){
    f.innerHTML='<button class="newdata" id="apply-new">Có dữ liệu mới — xem</button>';
    $("#apply-new").addEventListener("click",()=>{ if(paused){setPaused(false);$("#pause").textContent="Tạm dừng";
      $("#pause").setAttribute("aria-pressed","false");connect();} applyPending(); });
    return;
  }
  f.textContent=(paused?"đã dừng":drawerOpen?"tạm ngưng khi mở ngăn kéo":"cập nhật")+" · "+t;
}
