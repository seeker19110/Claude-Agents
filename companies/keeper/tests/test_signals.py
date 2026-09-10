from keeper.events import Signal
from keeper.signals import dedupe


def test_gom_trung() -> None:
    raw = [
        Signal(subject="pkg-a", kind="dependency", detail="lần 1", seen_count=1),
        Signal(subject="pkg-a", kind="dependency", detail="lần 2", seen_count=1),
        Signal(subject="pkg-a", kind="dependency", detail="lần 3 (mới nhất)", seen_count=1),
    ]

    assert len(raw) == 3          # mô tả đầu vào, KHÔNG phải ca chiều ngược (xem test dưới)

    out = dedupe(raw)
    assert len(out) == 1
    assert out[0].seen_count == 3
    assert out[0].detail == "lần 3 (mới nhất)"  # giữ bản mới nhất


def test_gom_trung_giu_nhom_khac_nhau() -> None:
    raw = [
        Signal(subject="pkg-a", kind="dependency", detail="a1"),
        Signal(subject="pkg-b", kind="dependency", detail="b1"),
        Signal(subject="pkg-a", kind="dependency", detail="a2"),
    ]
    out = dedupe(raw)
    assert [s.subject for s in out] == ["pkg-a", "pkg-b"]
    a = next(s for s in out if s.subject == "pkg-a")
    assert a.seen_count == 2
    assert a.detail == "a2"


def test_gom_trung_danh_sach_rong() -> None:
    assert dedupe([]) == []


def test_gom_trung_phan_biet_theo_kind() -> None:
    """Cùng `subject` nhưng khác `kind` KHÔNG được gộp — khoá gộp là `(kind, subject)`."""
    raw = [
        Signal(subject="x", kind="dependency", detail="d"),
        Signal(subject="x", kind="drift", detail="r"),
    ]
    out = dedupe(raw)
    assert len(out) == 2
    assert {s.seen_count for s in out} == {1}


def test_gom_trung_chieu_nguoc_khac_khoa_thi_khong_gop() -> None:
    """Ca chiều ngược THẬT của `dedupe`: nếu nó gộp theo thứ gì đó rộng hơn `(kind, subject)` — hoặc gộp mù mọi
    thứ về một — thì hai signal khác `subject` cũng bị nuốt và test này đỏ. `assert len(raw) == 3` ở test trên
    chỉ đếm fixture, không chạm `dedupe`, nên nó không đo được gì (khuôn lỗi đã mắc ở BT1)."""
    raw = [
        Signal(subject="pkg-a", kind="dependency", detail="a", seen_count=1),
        Signal(subject="pkg-b", kind="dependency", detail="b", seen_count=1),
        Signal(subject="pkg-a", kind="drift", detail="khác kind", seen_count=1),
    ]
    out = dedupe(raw)
    assert len(out) == 3                                  # ba khoá khác nhau → không gộp gì
    assert {s.seen_count for s in out} == {1}             # không cộng nhầm
    assert {(s.kind, s.subject) for s in out} == {
        ("dependency", "pkg-a"), ("dependency", "pkg-b"), ("drift", "pkg-a"),
    }
