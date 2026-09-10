/* loops.js — 4L-5: ô "vòng tool" (metrics.loops của xưởng phần mềm). Tách riêng khỏi tiles.js vì đây là màn
   mới (console/CLAUDE.md: "thêm màn mới: HTML + một module").

   ADR-0003: câu hỏi ô này trả lời — *agent cần bao nhiêu vòng tool để xong một lượt sản xuất, và bao lâu thì
   nó thua ở trần `max_turns`?* Ô KHÔNG BAO GIỜ xanh khi `loops.empty === true`: `capped_ratio` bằng 0 khi
   không có bản ghi nào trông giống "0% chạm trần, tốt" hệt như khi 50% lượt chạm trần thật — hai trạng thái
   phải tô khác nhau bằng mắt, không suy từ giá trị số (bẫy "số xanh vì rỗng", console/TRAPS.md). */
import {SC, srcOk, srcWhy, st} from "./state.js";
import {$, num, pctTxt} from "./util.js";

export function renderLoops(){
  const tile=$("#t-loop-tile"), v=$("#t-loop"), n=$("#t-loop-n");
  const any=srcOk(SC);
  const lp=any?st().loops:null;
  const empty=!lp||lp.empty!==false;   // thiếu nguồn HOẶC empty!==false đều coi là "chưa có gì để tô xanh"
  tile.classList.toggle("zero",empty);
  if(empty){
    v.textContent="—";
    n.textContent=any?"chưa có vòng tool nào đo được":srcWhy(SC);
    return;
  }
  v.textContent=num(lp.turns_p50);
  n.textContent=`p90 ${num(lp.turns_p90)} · trần ${num(lp.turns_max)} · chạm trần ${pctTxt(lp.capped_ratio)}`
    +(lp.retry_max_ratio!=null?` · ticket bị chặn ${pctTxt(lp.retry_max_ratio)}`:"")
    +(lp.no_progress_ratio!=null?` · không tiến triển ${pctTxt(lp.no_progress_ratio)}`:"");
}
