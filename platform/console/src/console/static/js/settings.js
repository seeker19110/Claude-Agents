/* settings.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
    */
import {api} from "./api.js";
import {titles} from "./router.js";
import {filter} from "./tiles.js";
import {$, $$, esc} from "./util.js";

/* ---------- cài đặt model ---------- */
export let CFG=null, CFG_ERR=null;
export const TIER_VI={strong:"mạnh",standard:"tiêu chuẩn",light:"nhẹ"};

export async function loadSettings(){
  try{ CFG=await api("/api/settings"); CFG_ERR=null; }
  catch(err){ CFG_ERR=err.message; }
  renderSettings(); titles();
}

export function renderSettings(){
  const box=$("#settings");
  if(CFG_ERR){ box.innerHTML=`<div class="empty">Không đọc được cấu hình: ${esc(CFG_ERR)}</div>`; return; }
  if(!CFG){ box.innerHTML='<div class="skel skel-line"></div>'; return; }
  const cat=CFG.catalog||[];
  const parts=[];
  for(const [company,e] of Object.entries(CFG.companies)){
    if(!e.ok){ parts.push(`<div class="sect-head"><h3>${esc(company)}</h3><p>${esc(e.error||"")}</p></div>`); continue; }
    const rows=e.backends.map(b=>{
      const tiers=CFG.tiers.map(t=>{
        const val=b.models[t]||"";
        // Backend đi qua gateway thì chọn từ danh sách gateway đang phục vụ; CLI thì gõ tay (model do CLI đó định nghĩa).
        const field=(b.via_gateway&&cat.length)
          ? `<select data-c="${esc(company)}" data-b="${esc(b.name)}" data-t="${t}">
               ${cat.concat(cat.includes(val)||!val?[]:[val]).map(m=>`<option${m===val?" selected":""}>${esc(m)}</option>`).join("")}
             </select>`
          : `<input data-c="${esc(company)}" data-b="${esc(b.name)}" data-t="${t}" value="${esc(val)}" size="24">`;
        return `<td><span class="note">${TIER_VI[t]}</span><br>${field}</td>`;
      }).join("");
      const warn=b.unknown.length?`<div class="note">⚠ gateway không phục vụ: ${esc(b.unknown.join(", "))}</div>`:"";
      return `<tr>
        <td><b>${esc(b.name)}</b><div class="note">${esc(b.provider)}${b.via_gateway?" · qua gateway":""}</div>${warn}</td>
        ${tiers}
        <td><label class="note"><input type="checkbox" data-toggle="${esc(company)}" data-b="${esc(b.name)}"${b.enabled?" checked":""}${CFG.can_edit?"":" disabled"}> đang bật</label></td>
      </tr>`;
    }).join("");
    const prefer=CFG.tiers.map(t=>{
      const cur=e.prefer[t]||"";
      const opts=[""].concat(e.backends.filter(b=>b.enabled).map(b=>b.name))
        .map(n=>`<option value="${esc(n)}"${n===cur?" selected":""}>${n?esc(n):"(không đặt)"}</option>`).join("");
      return `<label class="note">${TIER_VI[t]} <select data-prefer="${esc(company)}" data-t="${t}">${opts}</select></label>`;
    }).join(" ");
    parts.push(`
      <div class="sect-head"><h3>${esc(company)}</h3><p>${esc(e.path)}</p></div>
      <table><thead><tr><th>Backend</th>${CFG.tiers.map(t=>`<th>${TIER_VI[t]}</th>`).join("")}<th>Bật/tắt</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="filters">Ưu tiên backend theo tier: ${prefer}
        <button data-save="${esc(company)}"${CFG.can_edit?"":" disabled"}>Lưu</button>
        <span class="note" id="save-note-${esc(company)}"></span></div>`);
  }
  if(!CFG.can_edit) parts.unshift('<div class="note">Đang ở chế độ chỉ xem. Chạy lại: <code>python -m console --allow-config</code></div>');
  box.innerHTML=parts.join("");
}

$("#settings").addEventListener("click",async e=>{
  const btn=e.target.closest("[data-save]"); if(!btn) return;
  const company=btn.dataset.save, note=$("#save-note-"+CSS.escape(company));
  const models={};
  $$(`#settings [data-c="${CSS.escape(company)}"]`).forEach(el=>{
    (models[el.dataset.b]=models[el.dataset.b]||{})[el.dataset.t]=el.value.trim();
  });
  const prefer={}; $$(`#settings [data-prefer="${CSS.escape(company)}"]`).forEach(el=>{ if(el.value) prefer[el.dataset.t]=el.value; });
  const enable=[], disable=[];
  $$(`#settings [data-toggle="${CSS.escape(company)}"]`).forEach(el=>(el.checked?enable:disable).push(el.dataset.b));
  btn.disabled=true; note.textContent="đang lưu…";
  try{
    const r=await api("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({company,models,prefer,enable,disable})});
    note.textContent=r.changes.length?("đã lưu: "+r.changes.join("; ")):"không có gì thay đổi";
    await loadSettings();
  }catch(err){ note.textContent="lỗi: "+err.message; }
  finally{ btn.disabled=!CFG||!CFG.can_edit; }
});
