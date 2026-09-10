/* charts.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
    */
import {SC, emptyBox, st} from "./state.js";
import {filter} from "./tiles.js";
import {$, esc, vnd} from "./util.js";

/* ---------- biểu đồ ---------- */
export const tip=$("#tip");
export function showTip(html,x,y){tip.innerHTML=html;tip.classList.add("on");
  const r=tip.getBoundingClientRect();
  tip.style.left=Math.min(Math.max(8,x-r.width/2),innerWidth-r.width-8)+"px";
  tip.style.top=(y-r.height-12<8?y+16:y-r.height-12)+"px";}
export const hideTip=()=>tip.classList.remove("on");

export function costChart(){
  const cd=st().cost_days||{}, days=cd.series||[], labels=cd.days||[];
  const host=$("#chart-cost");
  if(!days.length){host.innerHTML=emptyBox(SC,"Chưa có ngày nào có chi phí");return;}
  const W=760,H=210,L=42,R=12,T=10,B=26, iw=W-L-R, ih=H-T-B;
  const tot=days.map(d=>d.reduce((a,b)=>a+b,0)), max=Math.max(.5,Math.ceil(Math.max(...tot)*2)/2);
  const bw=iw/days.length*.62, gap=iw/days.length;
  const y=v=>T+ih-v/max*ih;
  let g=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Chi phí theo ngày và tier">`;
  [0,max/2,max].forEach(t=>{g+=`<line x1="${L}" x2="${W-R}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)" stroke-width="1"/>
    <text x="${L-8}" y="${y(t)+4}" text-anchor="end" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="var(--axis)">${vnd(t)}</text>`;});
  days.forEach((d,i)=>{
    const x=L+gap*i+(gap-bw)/2; let acc=0;
    d.forEach((v,s)=>{const h=v/max*ih, yy=y(acc+v)+(s?1:0), hh=Math.max(1,h-(s?2:0));
      acc+=v;
      g+=`<rect x="${x}" y="${yy}" width="${bw}" height="${hh}" fill="var(--s${s+1})" ${s===2?'rx="3" ry="3"':""}/>`;});
    g+=`<rect class="hit" x="${L+gap*i}" y="${T}" width="${gap}" height="${ih}" fill="transparent" data-i="${i}" style="cursor:crosshair"/>`;
    if(i%2===1||i===days.length-1)g+=`<text x="${x+bw/2}" y="${H-8}" text-anchor="middle" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="var(--axis)">${esc(labels[i]||"")}</text>`;
  });
  const last=tot[tot.length-1];
  g+=`<text x="${L+gap*(days.length-1)+gap/2}" y="${y(last)-7}" text-anchor="middle" font-size="11" font-weight="600" font-family="IBM Plex Mono, monospace" fill="var(--ink)">${vnd(last)}</text>`;
  g+=`<line x1="${L}" x2="${W-R}" y1="${T+ih}" y2="${T+ih}" stroke="var(--axis)" stroke-width="1"/></svg>`;
  host.innerHTML=g;
  host.querySelectorAll(".hit").forEach(h=>{
    h.addEventListener("mousemove",ev=>{const i=+h.dataset.i,d=days[i];
      showTip(`<b>${esc(labels[i]||"")} · ${vnd(d.reduce((a,b)=>a+b,0))} USD</b>
        <div class="row"><i style="background:var(--s1)"></i><em>strong</em><s>${vnd(d[0])}</s></div>
        <div class="row"><i style="background:var(--s2)"></i><em>standard</em><s>${vnd(d[1])}</s></div>
        <div class="row"><i style="background:var(--s3)"></i><em>light</em><s>${vnd(d[2])}</s></div>`,ev.clientX,ev.clientY);});
    h.addEventListener("mouseleave",hideTip);});
}

export function agentChart(){
  const rows=st().agents||[], host=$("#chart-agent");
  if(!rows.length){host.innerHTML=emptyBox(SC,"Chưa có agent nào phát sinh chi phí");return;}
  const rowH=26, W=760, L=136, R=56, H=rows.length*rowH+16;
  const max=rows[0][1]||1;
  let g=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Chi phí theo agent">`;
  rows.forEach((a,i)=>{const w=(a[1]/max)*(W-L-R), yy=i*rowH+8;
    g+=`<text x="${L-10}" y="${yy+12}" text-anchor="end" font-size="12" font-family="IBM Plex Mono, monospace" fill="var(--ink-2)">${esc(a[0])}</text>
      <rect x="${L}" y="${yy}" width="${Math.max(3,w)}" height="15" rx="3" ry="3" fill="var(--s1)"/>
      <text x="${L+w+8}" y="${yy+12}" font-size="11.5" font-family="IBM Plex Mono, monospace" fill="var(--ink-2)">${vnd(a[1])}</text>`;});
  host.innerHTML=g+"</svg>";
}
