/* keeper.js — tab công ty bảo trì (BT8, `keeper/docs/DAC-TA-KEEPER.md` §10).

   Luật hiển thị của cả tab, một chỗ duy nhất: **chưa chạy lần nào thì không có số nào**.
   `collect.KeeperView.block()` đã quyết điều đó ở phía server (`ran`, `cards[].v === null`), module này chỉ
   được phép in `empty_note` thay cho số — không tự dựng một số 0 nào của riêng nó. Một số 0 màu xanh và một
   hệ thống chưa từng chạy nhìn giống hệt nhau (`console/TRAPS.md`, đêm vận hành QLKH 05/09).
    */
import {st} from "./state.js";
import {$, esc, hay, num} from "./util.js";

export const TIER={low:"thấp",medium:"vừa",high:"cao"};
export const kp=()=>st().keeper||{ran:false,empty_note:"chưa chạy lần nào",cards:[],tickets:[],debts:[],gates:[]};

/* Số của một ô — hoặc chữ "chưa chạy lần nào". `v == null` là CHƯA CHẠY; `v === 0` là đã chạy và đúng bằng 0. */
export const cardValue=c=>c.v==null?"—":num(c.v);

export function renderKeeper(){
  const k=kp(), note=k.empty_note||"chưa chạy lần nào";
  $("#kp-tiles").innerHTML=(k.cards||[]).map(c=>
    `<div class="tile"><span class="k">${esc(c.k)}</span><span class="v">${esc(cardValue(c))}</span>
      <span class="n">${esc(k.ran?c.n:note)}</span></div>`).join("");
  // Con số cạnh nút nav: `—` khi chưa chạy, chứ không phải 0 (cùng luật với các ô ở trên).
  $("#nav-keeper").textContent=k.ran?num((k.tickets||[]).length):"—";
  const rows=(k.tickets||[]).filter(t=>hay(t.id,t.subject,t.tier,t.st));
  $("#kp-tickets").innerHTML=rows.length?rows.map(t=>
    `<tr><td><code>${esc(t.id)}</code></td><td>${esc(t.subject)}</td>
      <td><span class="pill ${t.tier==="high"?"crit":t.tier==="medium"?"warn":"calm"}">${esc(TIER[t.tier]||t.tier)}</span></td>
      <td>${esc(t.st)}${t.gate?" · cần gate":""}</td><td>${esc(t.due||"—")}</td></tr>`).join("")
    :`<tr><td colspan="5"><div class="empty"><b>Không có ticket bảo trì nào đang chờ</b>${esc(k.ran?"vòng watch đã chạy — hàng đợi trống":note)}</div></td></tr>`;
  const debts=(k.debts||[]).filter(d=>hay(d.subject,d.reason,d.tier));
  $("#kp-debts").innerHTML=debts.length?debts.map(d=>
    `<tr><td>${esc(d.subject)}</td><td>${esc(d.reason)}</td><td>${esc(d.tier)}</td><td>${esc(d.due)}</td></tr>`).join("")
    :`<tr><td colspan="4"><div class="empty"><b>Không có nợ quá hạn</b>${esc(k.ran?"sổ nợ đọc được, chưa mục nào tới hạn":note)}</div></td></tr>`;
  $("#kp-gates").innerHTML=(k.gates||[]).length
    ?(k.gates||[]).map(g=>`<li><code>${esc(g.id)}</code> — gate ${esc(g.kind)}, ${num(g.hours)} giờ, tạo bởi <code>${esc(g.by)}</code>
       (duyệt ở màn Trực ban, hoặc <code>keeper gate approve ${esc(g.id)} --by human:&lt;tên&gt;</code>)</li>`).join("")
    :`<li class="empty"><b>Không có gate chờ</b>${esc(k.ran?"chưa ticket nào tới bậc rủi ro cần người ký":note)}</li>`;
}
