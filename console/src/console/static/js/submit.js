/* submit.js — tách từ index.html ở K7.1 (kịch bản B). Không build step, không CDN.
    */
import {CONSOLE, ME_KEY, READONLY, api} from "./api.js";
import {canEngine} from "./engine.js";
import {view} from "./router.js";
import {CFG} from "./settings.js";
import {filter} from "./tiles.js";
import {$, $$, esc} from "./util.js";

/* ---------- giao việc ----------
   Ba form = ba topic mà NGƯỜI được nạp vào bus (`console.submit.FORMS`), đặt NGAY TRONG màn của xưởng
   nhận việc (không gộp chung một màn): yêu cầu phần mềm + trả lời làm rõ ở Xưởng phần mềm, brief kênh ở
   Xưởng video. Trang chỉ gom trường thành payload đúng hình của schema topic; kiểm tra thật do bus của
   công ty làm khi publish, lỗi trả về nguyên văn. Danh sách (goals, pillars...): mỗi dòng một mục. */
export const SC_X="software-company", ST_X="Studio-creators";
export const FORMS=[
 {id:"req",xuong:SC_X,topic:"research-requests",title:"Yêu cầu phần mềm",view:"phan-mem",sample:true,
  hint:"Một dự án mới cho xưởng phần mềm: researcher tìm hiểu → spec-writer viết đặc tả → gate <b>spec</b> chờ bạn duyệt.",
  fields:[
   {k:"project_id",label:"Mã dự án",ph:"P1",req:true,mono:true},
   {k:"description",label:"Mô tả yêu cầu",ph:"Web bán khoá học tiếng Nhật: catalog, giỏ hàng, thanh toán VNPay, admin quản lý khoá. Mobile-first.",req:true,rows:6},
   {k:"repo",label:"Nơi lưu dự án — repo git của khách trên máy chạy orchestrator (đường dẫn tuyệt đối; bỏ trống = <code>--repo</code> mặc định của tiến trình)",ph:"D:\\khach\\web-khoa-hoc",mono:true},
   {k:"base",label:"Nhánh nền để rẽ nhánh tích hợp (bỏ trống = <code>--base</code> mặc định)",ph:"main",mono:true},
   {k:"attachments",label:"Tài liệu đính kèm (đường dẫn/URL, mỗi dòng một mục)",list:true,rows:2}]},
 {id:"ans",xuong:SC_X,topic:"clarification-answers",title:"Trả lời câu hỏi làm rõ",view:"phan-mem",
  hint:"Khi spec-writer đặt câu hỏi (topic <code>clarification-questions</code>), trả lời theo <code>question_id</code> để dự án đi tiếp.",
  fields:[
   {k:"project_id",label:"Mã dự án",ph:"P1",req:true,mono:true},
   {k:"answers",label:"Trả lời — mỗi dòng: <code>question_id: nội dung trả lời</code>",qa:true,req:true,rows:5,
    ph:"Q1: Thanh toán chỉ VNPay, chưa cần Momo\nQ2: Admin dùng chung tài khoản Google Workspace"}]},
 {id:"brief",xuong:ST_X,topic:"channel-briefs",title:"Brief kênh video",view:"video",
  hint:"Định hướng một kênh cho xưởng video: trend-researcher → channel-strategist lập kế hoạch → gate <b>plan</b> chờ bạn duyệt.",
  fields:[
   {k:"channel_id",label:"Mã kênh",ph:"CH1",req:true,mono:true},
   {k:"goals",label:"Mục tiêu (mỗi dòng một mục)",ph:"1000 subscriber trong 3 tháng",list:true,req:true,rows:2},
   {k:"audience",label:"Khán giả",ph:"người mới làm YouTube",req:true},
   {k:"pillars",label:"Trụ cột nội dung (mỗi dòng một mục)",ph:"hướng dẫn\nso sánh",list:true,req:true,rows:2},
   {k:"cadence",label:"Nhịp đăng",ph:"2 video/tuần"},
   {k:"boundaries",label:"Giới hạn (mỗi dòng một mục)",ph:"không hứa thu nhập\nkhông dùng nhạc chưa có license",list:true,rows:2},
   {k:"language",label:"Ngôn ngữ",ph:"vi"},
   {k:"tone",label:"Giọng điệu",ph:"gần gũi, thực tế"}]}];

export function renderSubmit(v){
  const sect=$(`#v-${v} .submit`); if(!sect) return;
  const box=$(".panel",sect); if(box.dataset.ready) return; box.dataset.ready="1";
  const xuong=sect.dataset.xuong, can=!!CONSOLE.can_submit;
  const me=esc(localStorage.getItem(ME_KEY)||"human:owner");
  const forms=FORMS.filter(f=>f.xuong===xuong).map(f=>`
    <form class="form" data-form="${f.id}" autocomplete="off">
      <div class="sect-head"><h3>${esc(f.title)}</h3><p>${f.hint} <span class="note">→ topic <code>${esc(f.topic)}</code> · ${esc(f.xuong)}</span></p></div>
      ${f.fields.map(x=>`<label class="fld"><span>${x.label}${x.req?' <b class="req">*</b>':""}</span>${
        x.rows?`<textarea name="${x.k}" rows="${x.rows}" placeholder="${esc(x.ph||"")}"${x.req?" required":""}></textarea>`
              :`<input name="${x.k}" placeholder="${esc(x.ph||"")}"${x.req?" required":""}${x.mono?' class="mono"':""}>`}</label>`).join("")}
      <div class="filters"><button type="submit"${can?"":" disabled"}>Giao việc</button>${
        f.sample?`<button type="button" data-sample>Điền yêu cầu mẫu</button>`:""}<span class="note" data-note></span></div>
    </form>`).join("");
  box.innerHTML=(can?"":'<div class="note">Đang ở chế độ chỉ xem. Chạy lại: <code>python -m console --allow-submit</code></div>')
    +`<div class="by">Bạn là <input class="submit-by" value="${me}" placeholder="human:owner"> <span class="note">ghi vào <code>actor</code> của event và audit-log</span></div>`
    +forms;
}

/* Yêu cầu mẫu: bản rút gọn của software-company/examples/yeu-cau-mau-web-app.json — giữ đủ tám phần mà `intake`
   cần để đặt câu hỏi cho cả bốn mảng domain/ux/codebase/tech. Người mới bấm một nút là có đề bài thật để sửa,
   thay vì nhìn ô trống rồi viết hai dòng mô tả mà spec-writer phải hỏi lại năm lần. */
export const REQ_SAMPLE={"project_id": "QLKH", "description": "Khách hàng: Trung tâm Anh ngữ Sao Mai (3 cơ sở, 40 giáo viên, 1200 học viên).\n\nBỐI CẢNH: đang quản lý bằng 6 file Excel dùng chung. Kế toán mất 3 ngày đối soát học phí mỗi tháng, tháng nào cũng có 5-10 học viên bị tính sai. Phụ huynh muốn biết con đi học đủ không phải nhắn Zalo hỏi.\n\nMỤC TIÊU (theo ưu tiên):\n1. Kế toán chốt học phí một tháng dưới 2 giờ thay vì 3 ngày, không sai sót thủ công.\n2. Phụ huynh tự xem điểm danh và lịch học của con.\n3. Giáo viên điểm danh trên điện thoại tại lớp, dưới 30 giây mỗi buổi.\n\nNGƯỜI DÙNG: giáo vụ (4, xếp lớp và đổi lịch), giáo viên (40, điện thoại Android tầm trung), kế toán (2, phiếu thu và công nợ), phụ huynh (~1000, chỉ đọc), quản lý (1, báo cáo tổng hợp).\n\nPHẠM VI BẢN ĐẦU: quản lý học viên/lớp/khoá/lịch tuần; điểm danh 4 trạng thái; học phí theo khoá hoặc buổi, chiết khấu anh chị em, phiếu thu, công nợ; cổng phụ huynh đăng nhập bằng OTP; báo cáo doanh thu, chuyên cần, công nợ quá hạn.\n\nNGOÀI PHẠM VI bản đầu: thi và chấm điểm online, học liệu số, app di động riêng (dùng web responsive), cổng thanh toán trực tuyến, chấm công và tính lương giáo viên.\n\nRÀNG BUỘC: ngân sách 180 triệu VND; 10 tuần tới khai giảng khoá hè; dữ liệu trẻ em phải theo Nghị định 13/2023, phụ huynh chỉ xem được dữ liệu con mình; phải import 6 file Excel hiện có kèm lịch sử học phí 2 năm; trung tâm không có đội IT nên ưu tiên dịch vụ managed; mạng cơ sở 3 chập chờn nên màn điểm danh phải dùng được khi mạng yếu và đồng bộ lại sau.\n\nPHI CHỨC NĂNG: màn điểm danh tải dưới 2 giây trên 3G máy Android tầm trung; chịu 60 giáo viên cùng điểm danh khung 17h30-18h00; sao lưu hằng ngày, khôi phục được trong 30 ngày; giao diện tiếng Việt, dùng được ở màn 360px.\n\nNGHIỆM THU: kế toán chốt được học phí tháng gần nhất bằng hệ thống mới và khớp với Excel cũ; 10 phụ huynh dùng thử xem đúng dữ liệu con mình.", "base": "main"};

export function fillSample(form){
  for(const [k,v] of Object.entries(REQ_SAMPLE)){
    const el=form.elements[k]; if(el) el.value=v;
  }
  const note=$("[data-note]",form);
  if(note) note.innerHTML='đã điền mẫu — sửa lại cho khách của bạn, nhớ điền <b>Nơi lưu dự án</b> nếu muốn code chạy trên repo thật';
  const first=form.elements.project_id; if(first) first.focus();
}

export function formPayload(f,form){
  const p={};
  for(const x of f.fields){
    const raw=(form.elements[x.k].value||"").trim();
    if(!raw){ if(x.req) throw new Error(`thiếu ${x.label.replace(/<[^>]+>/g,"")}`); continue; }
    if(x.qa){
      p[x.k]=raw.split("\n").map(s=>s.trim()).filter(Boolean).map(line=>{
        const i=line.indexOf(":"); if(i<1) throw new Error(`dòng "${line}" phải có dạng question_id: trả lời`);
        return {question_id:line.slice(0,i).trim(),answer:line.slice(i+1).trim()};
      });
    }
    else if(x.list) p[x.k]=raw.split("\n").map(s=>s.trim()).filter(Boolean);
    else p[x.k]=raw;
  }
  return p;
}

$$(".submit").forEach(sect=>sect.addEventListener("click",e=>{
  const btn=e.target.closest("button[data-sample]"); if(!btn) return;
  const form=btn.closest("form[data-form]"); if(form) fillSample(form);
}));

$$(".submit").forEach(sect=>sect.addEventListener("submit",async e=>{
  e.preventDefault();
  const form=e.target.closest("form[data-form]"); if(!form) return;
  const f=FORMS.find(x=>x.id===form.dataset.form), note=$("[data-note]",form), btn=$("button[type=submit]",form);
  const by=($(".submit-by",sect).value||"").trim(); if(!by){ note.textContent="điền Bạn là"; return; }
  localStorage.setItem(ME_KEY,by);
  let payload; try{ payload=formPayload(f,form); }catch(err){ note.textContent=err.message; return; }
  btn.disabled=true; note.textContent="đang gửi…";
  try{
    const r=await api("/api/request",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({xuong:f.xuong,topic:f.topic,payload,actor:by})});
    note.innerHTML=`đã giao: <code>${esc(r.key)}</code> · event <code>${esc(r.event_id)}</code> — xuất hiện ở bảng bên dưới khi orchestrator xử lý`;
    form.reset();
  }catch(err){ note.textContent="lỗi: "+err.message; }
  finally{ btn.disabled=!CONSOLE.can_submit; }
}));

/* ---------- hướng dẫn ---------- */
/* Bảng quyền nói đúng phiên NÀY đang mở gì, không phải danh sách cờ trong tài liệu: người mở console mà không
   bấm được nút nào thì câu trả lời phải nằm ngay trên màn, không phải trong README. */
export const CAPS=[
 {flag:"--allow-decide",what:"Duyệt gate ngay trong Trực ban (duyệt, trả lại, từ chối, giữ, thu hồi)",on:()=>!READONLY},
 {flag:"--allow-submit",what:"Giao việc mới cho hai xưởng và trả lời câu hỏi làm rõ",on:()=>!!CONSOLE.can_submit},
 {flag:"--allow-config",what:"Đổi model và backend của từng công ty ở Cài đặt model",on:()=>!!(CFG&&CFG.can_edit)},
 {flag:"--allow-engine",what:"Bật/tắt động cơ (orchestrator run --watch) của từng xưởng ở ô Động cơ — không bật động cơ thì việc giao và gate đã ký NẰM IM trên bus",on:()=>canEngine()}];

export function renderGuide(){
  const tb=$("#guide-caps"); if(!tb) return;
  tb.innerHTML=CAPS.map(c=>{
    const on=c.on();
    return `<tr><td><code>${esc(c.flag)}</code></td><td>${esc(c.what)}</td>
      <td class="${on?"cap-on":"cap-off"}">${on?"đang bật":"đang tắt — chạy lại console kèm cờ này"}</td></tr>`;
  }).join("");
}
