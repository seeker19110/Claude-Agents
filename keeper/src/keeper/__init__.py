"""`keeper` — công ty bảo trì tự vận hành, chạy trên chính repo X-Agents đang chứa nó.

Luật của package này (ADR `docs/adr/0006-cong-ty-bao-tri-keeper.md`, bất biến I1 ở
`keeper/docs/DAC-TA-KEEPER.md` §0):

- `keeper` KHÔNG có quyền ghi ra ngoài repo trừ ba việc: tạo nhánh, commit trong worktree của chính nó, và mở
  PR. Nó không bao giờ `gh pr merge`, không bao giờ `git push origin main`, không bao giờ tự đóng gate.
- Nó là khách hàng số 0 của chính nó (bất biến I7): mọi chu kỳ watch → triage → patch → verify → gate? →
  release trước tiên chạy trên chính X-Agents, không phải trên repo khách.
- Mọi patch phải có bằng chứng đo hai chiều (bất biến I2) trước khi rời pha quality; không có bằng chứng thì
  không có PR.
"""
from __future__ import annotations

__version__ = "0.1.0"
