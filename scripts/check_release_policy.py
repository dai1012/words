#!/usr/bin/env python3
"""发布端 release policy 检查：

1) entryID policy —— 所有 source 的 entryID：
   - 符合 schema 语法（与 build_catalog 相同正则）
   - 与词条正文内容无关（禁止出现 40+ 位十六进制内容 hash）
   - 同一 pack 内唯一
2) 引用路径存在性 —— source description 与 attribution/license 文件中引用的
   仓库内路径（`sources/...`、`packs/...` 等，以及反引号包裹的同目录文件名）
   必须真实存在（禁止 dead link）。外部 URL 仅列出、不联网校验。

用法：python3 scripts/check_release_policy.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_catalog import ENTRY_ID_PATTERN, repo_root  # noqa: E402

HASH_RE = re.compile(r"[0-9a-f]{40,}")
PATH_REF_RE = re.compile(r"(?:sources|packs|schemas|scripts)/[^\s`\"'，。；：、（）()\[\]]+")
BACKTICK_RE = re.compile(r"`([^`\s]+)`")
URL_RE = re.compile(r"https?://[^\s`\"'，。；：、（）()\[\]]+")


def strip_tail(text: str) -> str:
    return text.rstrip(".,;:。，；：、)]}）】》")


def check_entry_ids(root: Path) -> list:
    problems = []
    files = sorted(root.glob("sources/**/*.source.json"))
    total = 0
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        seen = set()
        for index, entry in enumerate(data.get("entries", [])):
            eid = entry.get("entryID", "")
            total += 1
            if not ENTRY_ID_PATTERN.match(eid):
                problems.append(f"{path}: entries[{index}].entryID 非法语法: {eid!r}")
            if HASH_RE.search(eid):
                problems.append(f"{path}: entries[{index}].entryID 含内容 hash: {eid!r}")
            if eid in seen:
                problems.append(f"{path}: 重复 entryID: {eid!r}")
            seen.add(eid)
    print(f"entryID policy: scanned {len(files)} packs / {total} entries")
    return problems


def iter_reference_docs(root: Path):
    """返回 (doc_path, text)：source descriptions + attribution/license 文件。"""
    docs = []
    for path in sorted(root.glob("sources/**/*.source.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        desc = (data.get("metadata") or {}).get("description")
        if desc:
            docs.append((path, desc))
    for path in sorted(root.glob("sources/**/*")):
        if path.is_file() and re.search(r"(?i)(attribution|license)", path.name):
            docs.append((path, path.read_text(encoding="utf-8")))
    return docs


def check_references(root: Path) -> list:
    problems = []
    urls = set()
    checked = 0
    for doc, text in iter_reference_docs(root):
        # 先遮蔽 URL，避免把 URL 路径片段（如 digital.go.jp/resources/...）
        # 误判为仓库内相对路径引用。
        masked = URL_RE.sub(lambda m: " " * len(m.group(0)), text)
        candidates = set()
        for match in PATH_REF_RE.finditer(masked):
            candidates.add((strip_tail(match.group(0)), None))
        for match in BACKTICK_RE.finditer(masked):
            token = match.group(1)
            if "/" in token:
                continue
            if "." in token:
                candidates.add((token, doc.parent))
        for ref, base in sorted(candidates):
            target = (base / ref) if base else (root / ref)
            checked += 1
            if not target.exists():
                problems.append(f"{doc}: dead reference -> {ref}")
        for match in URL_RE.finditer(text):
            urls.add(strip_tail(match.group(0)))
    print(f"reference check: scanned {checked} repo-relative refs")
    print(f"external URLs referenced (not fetched): {len(urls)}")
    for url in sorted(urls):
        print(f"  URL {url}")
    return problems


def main() -> int:
    root = repo_root()
    problems = check_entry_ids(root) + check_references(root)
    if problems:
        print("RELEASE_POLICY: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("RELEASE_POLICY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
