"""One-time transport helper, excluded from the final PR tree and history.

Copies pinned public Git blobs and applies reviewed line edits. Does not import
or execute application code, run tests with write credentials, or alter main.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

BASE = "b84dcb76b9085a686dafae97f47c988ac872446a"
OLD = "0c99bb42bf63bee3a6fa6778f45e78e535a66137"
ADR = "f9c33f996c9cf165d9a90318b92ff23ef7f0926f"
BRANCH = "feat/product-quality-harness"
assert os.environ["GITHUB_REPOSITORY"] == "seeker19110/Claude-Agents"
assert os.environ["GITHUB_REF"] == "refs/heads/" + BRANCH


def git(*args):
    return subprocess.check_output(["git", *args])


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


spec = json.loads(Path(".integration/transfer.json").read_text(encoding="utf-8"))
assert len(spec["files"]) == 20
for remote, ref in [("origin", BASE), ("origin", ADR),
                    ("https://github.com/seeker19110/X-Agents.git", OLD)]:
    git("fetch", "--no-tags", remote, ref)
for item in spec["adapt"]:
    assert item["ref"] in {BASE, OLD, ADR}
    assert item["path"] in spec["files"]
    path = Path(item["path"])
    assert not path.is_absolute() and ".." not in path.parts
    source = git("show", item["ref"] + ":" + item["source"])
    assert blob(source) == item["sha"], "source mismatch: " + item["path"]
    lines = source.decode("utf-8").splitlines(keepends=True)
    limit = len(lines)
    for start, end, text in reversed(item["edits"]):
        assert 0 <= start <= end <= limit
        lines[start:end] = text.splitlines(keepends=True)
        limit = start
    result = "".join(lines).encode("utf-8")
    assert blob(result) == spec["files"][item["path"]], "adapted mismatch: " + item["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result)
for path, expected in spec["files"].items():
    actual = blob(Path(path).read_bytes())
    assert actual == expected, f"final mismatch: {path}: {actual} != {expected}"
    print(expected, path)
git("diff", "--check")
git("add", "--", *spec["files"])
staged = set(git("diff", "--cached", "--name-only").decode().splitlines())
assert staged <= set(spec["files"])
assert staged, "no source changes to assemble"
git("-c", "user.name=seeker19110", "-c", "user.email=29851712+seeker19110@users.noreply.github.com",
    "commit", "-m", "feat(company): assemble verified native product quality integration")
git("push", "origin", "HEAD:refs/heads/" + BRANCH)
print("ASSEMBLED_COMMIT", git("rev-parse", "HEAD").decode().strip())
