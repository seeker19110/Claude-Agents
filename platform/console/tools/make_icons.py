"""Sinh icon PNG cho manifest PWA — chỉ thư viện chuẩn, không Pillow.

Chạy lại: `PYTHONPATH=src uv run python tools/make_icons.py`. Kết quả được commit, nên CI
không phải sinh lại; script ở đây để icon có thể tái tạo chứ không phải là một file nhị phân
rơi từ trên trời xuống.

Icon cố ý **full-bleed, không bo góc**: manifest khai `purpose: "any maskable"`, và hệ điều
hành sẽ tự cắt theo hình dạng của nó (tròn trên Android, bo góc trên Windows). Tự bo góc trước
sẽ bị cắt hai lần.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "console" / "static"

BG = (10, 17, 28)          # --ground của chủ đề tối: xanh navy
BARS = [
    (0.28, (16, 185, 129)),   # --accent, xanh lá
    (0.46, (240, 180, 41)),   # --warn, vàng: hàng đợi đang chờ người duyệt
    (0.64, (163, 179, 201)),  # --ink-2, xám xanh
]
BAR_H = 0.10
BAR_X0, BAR_X1 = 0.24, 0.76
SHORT_X1 = 0.60            # vạch thứ ba ngắn hơn, giống favicon nội tuyến trong index.html


def render(size: int) -> bytes:
    """Trả về các dòng pixel RGB thô. Không khử răng cưa: mọi cạnh đều nằm ngang/dọc."""
    rows: list[bytearray] = []
    for y in range(size):
        row = bytearray()
        fy = y / size
        colour = BG
        x_from, x_to = 0.0, 0.0
        for top, bar_colour in BARS:
            if top <= fy < top + BAR_H:
                colour = bar_colour
                x_from, x_to = BAR_X0, (SHORT_X1 if bar_colour == BARS[2][1] else BAR_X1)
                break
        for x in range(size):
            fx = x / size
            row += bytes(colour if (colour is not BG and x_from <= fx < x_to) else BG)
        rows.append(row)
    return b"".join(b"\x00" + bytes(r) for r in rows)   # \x00 = filter "None" mỗi dòng


def png(size: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)   # 8-bit, truecolour RGB
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(render(size), 9)) + chunk(b"IEND", b""))


def main() -> None:
    for size in (192, 512):
        target = OUT / f"icon-{size}.png"
        target.write_bytes(png(size))
        print(f"{target.name}: {target.stat().st_size} byte")


if __name__ == "__main__":
    main()
