r"""DoD — cổng chặn PR merge khi ô "Definition of Done" hay "BÁO CÁO XÁC THỰC" còn mở.

Python stdlib thuần, chạy được bằng `python3 scripts/pr_dod_check.py`.
Đọc thân PR từ biến môi trường `BODY`.
Tìm các ô còn mở `^\s*[-*]\s+\[ \]` trong mục DoD hoặc BÁO CÁO XÁC THỰC.
Bỏ qua ô có `(sau merge)`.
Exit 1 và in danh sách ô mở trên stderr, hoặc exit 0.
"""
from __future__ import annotations

import os
import re
import sys


def open_items(body: str) -> list[str]:
    """Tìm các ô còn mở trong 'Definition of Done' và 'BÁO CÁO XÁC THỰC'.

    Args:
        body: Thân PR.

    Returns:
        Danh sách các ô mở (nội dung, không có `- [ ]`).
    """
    # Chuẩn hoá \r\n
    body = body.replace("\r\n", "\n")

    # Tách các mục bằng regex tìm heading level 2
    sections = {}
    current_section = None
    current_content = []

    for line in body.split("\n"):
        # Kiểm heading level 2 (##) nhưng không phải level 1 (#)
        # Nên kiểm xem nó bắt đầu bằng ## nhưng không bắt đầu bằng ###
        if line.startswith("##") and not line.startswith("###"):
            # Lưu mục trước
            if current_section:
                sections[current_section] = "\n".join(current_content)
            # Bắt đầu mục mới
            current_section = line[2:].strip()
            current_content = []
        elif current_section:
            # Thêm dòng vào nội dung mục (bao gồm cả heading level 3+)
            current_content.append(line)

    # Lưu mục cuối cùng
    if current_section:
        sections[current_section] = "\n".join(current_content)

    # Tìm mục DoD và BÁO CÁO
    open_item_list = []

    # Khớp mục "Definition of Done" chính xác
    for section_name, section_content in sections.items():
        if section_name == "Definition of Done":
            items = _extract_open_items(section_content)
            open_item_list.extend(items)

    # Khớp mục "BÁO CÁO XÁC THỰC" (có thể có tiền tố)
    for section_name, section_content in sections.items():
        if section_name.startswith("BÁO CÁO XÁC THỰC"):
            items = _extract_open_items(section_content)
            open_item_list.extend(items)

    return open_item_list


def _extract_open_items(content: str) -> list[str]:
    r"""Trích xuất các ô mở từ nội dung một mục.

    Ô mở = dòng khớp `^\s*[-*]\s+\[ \]`.
    Bỏ qua ô có `(sau merge)`.

    Args:
        content: Nội dung của mục (không gồm heading).

    Returns:
        Danh sách các ô mở.
    """
    items = []
    checkbox_pattern = re.compile(r"^\s*[-*]\s+\[\s\]\s*(.+)$")

    for line in content.split("\n"):
        m = checkbox_pattern.match(line)
        if m:
            item_text = m.group(1)
            # Bỏ qua nếu có (sau merge)
            if "(sau merge)" not in item_text:
                items.append(item_text)

    return items


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None) -> int:
    """Kiểm DoD và BÁO CÁO, trả exit code.

    Args:
        argv: Danh sách argument (hiện không dùng).
        environ: Dict môi trường (mặc định dùng os.environ).

    Returns:
        0 nếu không có ô mở, 1 nếu có.
    """
    if environ is None:
        environ = os.environ

    body = environ.get("BODY", "")
    items = open_items(body)

    if items:
        # Runner Windows để stderr ở cp1252: ô tiếng Việt thành `\\u0111` trong log. Luôn ghi UTF-8.
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        for item in items:
            print(item, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
