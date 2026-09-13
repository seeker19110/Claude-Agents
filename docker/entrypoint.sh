#!/usr/bin/env sh
# ADR-0013: entrypoint container hub. Ghi git identity từ env nếu có (orchestrator commit thật lên repo khách
# khi tạo/gộp worktree), rồi chạy console — console tự spawn orchestrator qua --allow-engine (ADR-0004),
# argv chốt cứng trong platform/console/src/console/engine.py, không đọc gì từ đây.
set -eu

if [ -n "${GIT_AUTHOR_NAME:-}" ] && [ -n "${GIT_AUTHOR_EMAIL:-}" ]; then
    git config --global user.name "$GIT_AUTHOR_NAME"
    git config --global user.email "$GIT_AUTHOR_EMAIL"
fi

# --i-know không cần vì mặc định bind 127.0.0.1 — WSL2 tự forward cổng cho host, xem ADR-0013 quyết định 6.
CONSOLE_ARGS="--allow-decide --allow-submit --allow-config --allow-engine"
if [ -n "${DELIVER_REMOTE:-}" ]; then
    CONSOLE_ARGS="$CONSOLE_ARGS --deliver-remote ${DELIVER_REMOTE}"
fi

cd /app/platform/console
# shellcheck disable=SC2086
exec uv run python -m console $CONSOLE_ARGS "$@"
