/* state.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
    */
import {api} from "./api.js";
import {drawer} from "./drawer.js";
import {stream} from "./stream.js";
import {$, esc, setQ} from "./util.js";

/* ---------- trạng thái ---------- */
export const SC="software-company", ST="Studio-creators", KP="keeper", GW="gateway";
export const BLANK={generated_at:null,sources:{},tiles:{},gates:[],tickets:[],prs:[],reviews:[],videos:[],perf:[],
  retention:null,cost_days:{days:[],series:[]},agents:[],backends:[],supervisor:[],log:[],
  delivery:null,pending_decisions:[],running:null,deadlocks:[],product_funnel:[],silent_deadlocks:[],sandbox:null,
  loops:null,keeper:null};
export let S=null;                    // dữ liệu tốt lần cuối đọc được — giữ nguyên khi lỗi
export let firstLoad=true, paused=false, drawerOpen=false, lastOk=null, timer=null;
export const st=()=>S||BLANK;
export const NOT_READ="chưa đọc được /api/state";
export function source(k){
  const s=(st().sources||{})[k];
  if(!s) return {ok:false,error:S?"nguồn này không có trong /api/state":NOT_READ};
  return s;
}
export const srcOk=k=>source(k).ok===true;
export const srcWhy=k=>source(k).error||"chưa có dữ liệu";
export function emptyBox(k,what){return `<div class="empty"><b>${esc(what)}</b>${esc(srcWhy(k))}</div>`;}
export function emptyRow(cols,k,what){return `<tr><td colspan="${cols}" style="padding:0">${emptyBox(k,what)}</td></tr>`;}
export const listOf=(k,arr)=>srcOk(k)?(arr||[]):[];     // nguồn hỏng thì không vẽ số nào của nó

/* ---------- dải cảnh báo ---------- */
export function banner(msg,note){
  const b=$("#banner");
  if(!msg){b.classList.remove("on");return;}
  b.classList.add("on"); $("#banner-msg").textContent=msg; $("#banner-note").textContent=note||"";
}

/* `stream`/`drawer` gán lại sau mỗi vòng đọc và mỗi lần mở ngăn kéo; xem setQ ở util.js. */
export function setS(v){ S=v; }
export function setFirstLoad(v){ firstLoad=v; }
export function setPaused(v){ paused=v; }
export function setDrawerOpen(v){ drawerOpen=v; }
export function setLastOk(v){ lastOk=v; }
export function setTimer(v){ timer=v; }
