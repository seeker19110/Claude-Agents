"""ADR-0046: bằng chứng chuỗi cung ứng (SBOM + license) của một cây RC, do orchestrator sinh — không phải lời khai.

Thành phần đọc từ `uv.lock` bằng `tomllib` (không chạy gì). License đọc từ metadata gói đã cài trong môi trường của
KHÁCH (`uv run --frozen`, ADR-0044) qua sandbox (ADR-0035). Chuẩn hoá sang SPDX chỉ khi không mơ hồ; còn lại là
`NOASSERTION` kèm chuỗi gốc — không đoán. Không kết luận hợp lệ hay không: đó là chính sách của dự án.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from .sandbox import RunSpec, clean_env
from .smoke import VERIFIED_BY, unverified

NOASSERTION = "NOASSERTION"

# Chạy trong venv của khách: in {tên PEP 503: chuỗi license gốc}. PEP 639 → classifier → trường `License`.
_SCRIPT = (
    "import importlib.metadata as m, json, re\n"
    "out = {}\n"
    "for d in m.distributions():\n"
    "    md = d.metadata\n"
    "    name = re.sub(r'[-_.]+', '-', md.get('Name') or '').lower()\n"
    "    if not name: continue\n"
    "    lic = (md.get('License-Expression') or '').strip()\n"
    "    if not lic:\n"
    "        lic = ' OR '.join(c.split('::')[-1].strip() for c in (md.get_all('Classifier') or []) if c.startswith('License ::'))\n"
    "    if not lic: lic = (md.get('License') or '').strip()\n"
    "    out[name] = lic.splitlines()[0][:200] if lic else ''\n"
    "print(json.dumps(out))\n"
)

# Tên gọi không mơ hồ → SPDX id. "BSD License", "Apache Software License" không nói phiên bản: không có ở đây.
_NAMES = {
    "mit": "MIT",
    "mit license": "MIT",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache license version 2.0": "Apache-2.0",
    "apache software license 2.0": "Apache-2.0",
    "new bsd license": "BSD-3-Clause",
    "modified bsd license": "BSD-3-Clause",
    "3-clause bsd license": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "simplified bsd license": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "isc license": "ISC",
    "isc license (iscl)": "ISC",
    "python software foundation license": "PSF-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "the unlicense (unlicense)": "Unlicense",
}
_SPDX_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")
_AMBIGUOUS = frozenset({"BSD", "GPL", "LGPL", "AGPL", "Apache", "Proprietary", "UNKNOWN", "Other"})
_OPS = frozenset({"AND", "OR", "WITH"})


def _pep503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def spdx_of(raw: str) -> str:
    """Chuỗi license gốc → SPDX (id hoặc biểu thức) khi không mơ hồ; ngược lại `NOASSERTION`."""
    s = raw.strip()
    if not s:
        return NOASSERTION
    if (named := _NAMES.get(s.lower())) is not None:
        return named
    toks = s.split()
    ids = [t.strip("()") for t in toks[0::2]]
    if all(op in _OPS for op in toks[1::2]) and all(_SPDX_ID.fullmatch(i) and i not in _AMBIGUOUS for i in ids):
        return s
    return NOASSERTION


def components(root: Path) -> list[dict[str, str]] | None:
    """Gói trong `uv.lock` (trừ gói gốc/workspace). Không có lock → None."""
    lock = root / "uv.lock"
    if not lock.is_file():
        return None
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    out = []
    for pkg in data.get("package", []):
        src = pkg.get("source") or {}
        if "editable" in src or "virtual" in src:
            continue
        name, version = _pep503(str(pkg.get("name", ""))), str(pkg.get("version", ""))
        out.append({"name": name, "version": version, "purl": f"pkg:pypi/{name}@{version}"})
    return out


def installed_licenses(root: Path, sandbox: Any) -> tuple[dict[str, str], str | None]:
    """License gốc của mọi gói đã cài trong môi trường của khách. Lỗi → ({}, lý do), không ném."""
    spec = RunSpec(
        argv=["uv", "run", "--frozen", "--", "python", "-c", _SCRIPT],
        cwd=root,
        env=clean_env(),
        timeout=600.0,
        max_output=2_000_000,
    )
    try:
        r = sandbox.run(spec)
    except OSError as e:
        return {}, f"{type(e).__name__}: {e}"[:300]
    if r.exit_code != 0:
        return {}, f"exit_code={r.exit_code}: {r.stderr.strip()[-300:]}"
    try:
        data = json.loads(r.stdout)
    except ValueError:
        return {}, f"stdout không phải JSON: {r.stdout.strip()[:200]}"
    return {str(k): str(v) for k, v in data.items()}, None


def evidence(root: Path, sandbox: Any, sha: str) -> dict[str, Any]:
    """Bằng chứng `evidence.supply_chain` của cây RC `root` (ADR-0046 §1, §4)."""
    comps = components(root)
    if comps is None:
        return unverified("cây RC không có `uv.lock` — ADR-0046 chỉ đọc lock của uv")
    lic, err = installed_licenses(root, sandbox)
    rows = []
    for c in comps:
        raw = lic.get(c["name"])
        rows.append(
            {
                **c,
                "license": spdx_of(raw or ""),
                "raw": raw or "",
                "installed": (raw is not None) if err is None else None,
            }
        )
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": r["name"],
                "version": r["version"],
                "purl": r["purl"],
                "licenses": [] if r["license"] == NOASSERTION else [{"expression": r["license"]}],
            }
            for r in rows
        ],
    }
    digest = hashlib.sha256(json.dumps(sbom, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    ev: dict[str, Any] = {
        "verified_by": VERIFIED_BY,
        "source": "uv.lock",
        "sha": sha,
        "components": len(rows),
        "licenses": dict(Counter(r["license"] for r in rows)),
        "noassertion": [
            {k: r[k] for k in ("name", "version", "raw", "installed")} for r in rows if r["license"] == NOASSERTION
        ],
        "copyleft": [
            {k: r[k] for k in ("name", "version", "license", "raw")}
            for r in rows
            if re.search(r"GPL|GENERAL PUBLIC|SSPL", f"{r['raw']} {r['license']}".upper())
        ],
        "sbom_ref": f"sha256:{digest}",
        "sbom": sbom,
    }
    if err is not None:
        ev["licenses_error"] = err
    return ev
