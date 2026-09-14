#!/usr/bin/env bash
# dev-task.sh — MỘT điểm vào cho mọi lệnh cổng của workspace.
#
# Vì sao tồn tại: `AGENTS.md` luật bắt buộc 3 nói "chạy đúng lệnh CI trước khi push", nhưng lệnh đó là BA dòng
# khác nhau, nhân năm package, và software-company còn thêm `-n auto --cov`. Chỗ nào phải nhớ, chỗ đó agent sẽ
# nhớ sai — và cổng cục bộ lệch cổng CI thì PR đỏ sau khi đã push. Ở đây: `dev-task.sh gate` là đủ.
#
# Lấy ý tưởng từ `seeker19110/project-template` (`scripts/dev-task.sh`), nhưng KHÔNG tự dò hệ sinh thái: repo
# này chỉ có một stack (uv workspace, năm package Python) nên bảng tra tường minh đúng hơn phép dò — dò sai
# thì nó chạy một lệnh KHÁC lệnh CI mà không ai biết.
#
# Dùng:  scripts/dev-task.sh <task> [gói]
#   task: format | format-file <path> | lint | typecheck | test | gate
#   gói : company | gateway | console | core | keeper | all (mặc định: all)
#   gate = lint → typecheck → test, đỏ một bước là dừng ngay ở bước đó.
#
# DEV_TASK_DRY_RUN=1 → chỉ IN lệnh sẽ chạy, không chạy. Dùng cho test và cho lúc muốn xem trước.
set -uo pipefail   # cố ý KHÔNG -e: script tự kiểm mã trả về từng bước, -e sẽ cắt mất dòng tổng kết

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
TASK="${1:-}"
ARG="${2:-}"

log() { printf '[dev-task] %s\n' "$*" >&2; }

# Bảng tra: gói → "thư mục|module mypy". Thứ tự này cũng là thứ tự chạy của `all`.
GOI_LIST="company gateway console core keeper"
goi_thu_muc() {
  case "$1" in
    company) echo "companies/software-company" ;;
    gateway) echo "platform/gateway" ;;
    console) echo "platform/console" ;;
    core)    echo "platform/xagents-core" ;;
    keeper)  echo "companies/keeper" ;;
    *)       return 1 ;;
  esac
}
goi_module() {
  case "$1" in
    company) echo "company" ;;
    gateway) echo "gateway" ;;
    console) echo "console" ;;
    core)    echo "xagents_core" ;;
    keeper)  echo "keeper" ;;
    *)       return 1 ;;
  esac
}

# Lệnh test phải khớp ĐÚNG `.github/workflows/ci.yml`, không phải "gần đúng": `--cov` cho cả năm gói (thiếu nó
# thì `fail_under = 100` không có hiệu lực và cổng cục bộ xanh trong khi CI đỏ), `-n auto` chỉ software-company.
goi_lenh_test() {
  if [ "$1" = "company" ]; then
    echo "uv run pytest -q -n auto --cov --cov-report=term-missing"
  else
    echo "uv run pytest -q --cov --cov-report=term-missing"
  fi
}

lenh_cho() {
  # $1 = task, $2 = gói. In ra lệnh, hoặc rỗng nếu task không áp dụng.
  case "$1" in
    lint)      echo "uv run ruff check src tests" ;;
    format)    echo "uv run ruff format src tests" ;;
    typecheck) echo "uv run mypy src/$(goi_module "$2") --ignore-missing-imports" ;;
    test)      goi_lenh_test "$2" ;;
    *)         return 1 ;;
  esac
}

chay_trong_goi() {
  # $1 = task, $2 = gói. Trả về mã thoát của lệnh (0 khi dry-run).
  local task="$1" goi="$2" thu_muc lenh
  thu_muc="$(goi_thu_muc "$goi")" || { log "gói lạ: $goi"; return 2; }
  lenh="$(lenh_cho "$task" "$goi")" || return 2

  if [ "${DEV_TASK_DRY_RUN:-0}" = "1" ]; then
    printf '%s: %s\n' "$thu_muc" "$lenh"
    return 0
  fi

  log "$thu_muc: $lenh"
  ( cd "$ROOT/$thu_muc" && eval "$lenh" )
}

goi_can_chay() {
  # $1 = tham số gói của người gọi ('' hoặc 'all' → cả năm).
  if [ -z "$1" ] || [ "$1" = "all" ]; then echo "$GOI_LIST"; else echo "$1"; fi
}

chay_task() {
  # $1 = task, $2 = tham số gói. Đỏ ở gói nào thì dừng ngay ở gói đó.
  local task="$1" goi
  for goi in $(goi_can_chay "$2"); do
    chay_trong_goi "$task" "$goi" || return $?
  done
}

case "$TASK" in
  "")
    log "thiếu tên task. Dùng: dev-task.sh format|format-file|lint|typecheck|test|gate [gói]"
    exit 2
    ;;

  format-file)
    # Format đúng MỘT file vừa sửa (hook PostToolUse gọi). Chỉ .py — ruff không đụng file khác.
    [ -n "$ARG" ] || { log "format-file cần đường dẫn"; exit 2; }
    case "$ARG" in
      *.py)
        if [ "${DEV_TASK_DRY_RUN:-0}" = "1" ]; then printf 'uv run ruff format %s\n' "$ARG"; exit 0; fi
        ( cd "$ROOT" && uv run ruff format "$ARG" >/dev/null 2>&1 ) || true
        ;;
      *) : ;;   # không phải Python → không có formatter nào áp dụng, im lặng bỏ qua
    esac
    exit 0
    ;;

  lint|format|typecheck|test)
    chay_task "$TASK" "$ARG"
    exit $?
    ;;

  gate)
    # Thứ tự cố định lint → typecheck → test: bước rẻ chạy trước, đỏ thì khỏi chờ pytest.
    for buoc in lint typecheck test; do
      chay_task "$buoc" "$ARG" || { log "CỔNG ĐỎ ở bước: $buoc"; exit 1; }
    done
    log "cổng XANH (lint + typecheck + test)"
    exit 0
    ;;

  *)
    log "task lạ: $TASK. Dùng: format|format-file|lint|typecheck|test|gate"
    exit 2
    ;;
esac
