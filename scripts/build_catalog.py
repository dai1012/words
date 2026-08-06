#!/usr/bin/env python3
"""生成 packs/*.json 与 catalog.json。

契约（与 JapaneseWordWatch Issue 005/006 对齐，见 schemas/README.md）：
- source 只负责可编辑字段；entryCount / fileSize / SHA-256 / catalog descriptor
  全部由本脚本从最终落盘的 pack 原始 bytes 计算。
- 确定性序列化：UTF-8、sort_keys、indent=2、行尾 LF，保证重复构建 byte-identical。
- packVersion 只来自 source，脚本绝不修改；source 内容变化但 packVersion 未提升
  时 fail closed。
- catalogVersion/generatedAt：catalog 内容未变化时原样复用旧值（幂等）；
  内容变化时 catalogVersion+1、generatedAt 取当前 UTC。
- 全部校验通过后原子替换输出；任何失败非零退出且不留下半生成结果。

用法：
    python3 scripts/build_catalog.py            # 构建并原子落盘
    python3 scripts/build_catalog.py --check    # 构建到内存，与现有文件逐字节比较，不写盘

环境变量（供 CI/多目录场景）：
    WORDS_REPO_ROOT    仓库根目录（默认本脚本所在目录的上级）
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# 所有 descriptor 共用：当前 App 可兼容的最低版本（MARKETING_VERSION 1.0.0）。
# App 提高版本要求时在此提升，并同步提升需要新门槛的 pack 的 packVersion。
MINIMUM_APP_VERSION = "1.0.0"

SCHEMA_VERSION = 1

# Issue 005 grammar（与 RemoteWordPackGrammar 逐条对应）
PACK_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
ENTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)$")


class BuildError(Exception):
    pass


def repo_root() -> Path:
    if os.environ.get("WORDS_REPO_ROOT"):
        return Path(os.environ["WORDS_REPO_ROOT"]).resolve()
    return Path(__file__).resolve().parent.parent


def serialize(obj) -> bytes:
    """确定性序列化：UTF-8、sort_keys、indent=2、LF 结尾。"""
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    return text.encode("utf-8") + b"\n"


def is_blank(value: str) -> bool:
    return value.strip() == ""


def load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise BuildError(f"{path}: 无法解析 JSON: {e}")
    if not isinstance(data, dict):
        raise BuildError(f"{path}: 根必须是对象")
    return data


def validate_optional_field(name: str, value, required: bool) -> dict:
    """catalog/pack 可选字段：缺失省略 key；显式 null 被 App v1 拒绝。"""
    if value is None:
        raise BuildError(f"{name}: 显式 null 非法，必须省略该字段")
    if required and is_blank(str(value)):
        raise BuildError(f"{name}: 必填字段不能为空白")
    return {name: value}


def validate_entries(entries, pack_id: str) -> None:
    if not isinstance(entries, list) or not entries:
        raise BuildError(f"{pack_id}: entries 必须是非空数组")
    seen = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise BuildError(f"{pack_id}: entries[{index}] 必须是对象")
        entry_id = entry.get("entryID")
        if not isinstance(entry_id, str) or not ENTRY_ID_PATTERN.match(entry_id):
            raise BuildError(f"{pack_id}: entries[{index}].entryID 非法: {entry_id!r}")
        if entry_id in seen:
            raise BuildError(f"{pack_id}: 重复 entryID: {entry_id}")
        seen.add(entry_id)
        for key in ("term", "reading", "meaning"):
            value = entry.get(key)
            if not isinstance(value, str):
                raise BuildError(f"{pack_id}: entries[{index}].{key} 缺失或非字符串")
            if is_blank(value):
                # reading 例外："" 合法；非空纯空白非法。
                if key != "reading" or value != "":
                    raise BuildError(f"{pack_id}: entries[{index}].{key} 不能为空白")


def validate_metadata(metadata: dict, pack_id: str) -> None:
    if not isinstance(metadata, dict):
        raise BuildError(f"{pack_id}: metadata 必须是对象")
    title = metadata.get("title")
    if not isinstance(title, str) or is_blank(title):
        raise BuildError(f"{pack_id}: metadata.title 必填且非空白")
    language = metadata.get("language")
    if not isinstance(language, str) or not LANGUAGE_PATTERN.match(language):
        raise BuildError(f"{pack_id}: metadata.language 非法: {language!r}")
    classification = metadata.get("classification")
    if not isinstance(classification, str) or not SLUG_PATTERN.match(classification):
        raise BuildError(f"{pack_id}: metadata.classification 非法: {classification!r}")
    level = metadata.get("level")
    if level is not None and (not isinstance(level, str) or not SLUG_PATTERN.match(level)):
        raise BuildError(f"{pack_id}: metadata.level 非法: {level!r}")
    description = metadata.get("description")
    if description is not None and (not isinstance(description, str) or is_blank(description)):
        raise BuildError(f"{pack_id}: metadata.description 非法: {description!r}")
    tags = metadata.get("tags", [])
    if not isinstance(tags, list):
        raise BuildError(f"{pack_id}: metadata.tags 必须是数组")
    seen = set()
    for index, tag in enumerate(tags):
        if not isinstance(tag, str) or not SLUG_PATTERN.match(tag):
            raise BuildError(f"{pack_id}: metadata.tags[{index}] 非法: {tag!r}")
        if tag in seen:
            raise BuildError(f"{pack_id}: 重复 tag: {tag}")
        seen.add(tag)


def relative_path(path: Path, root: Path) -> str:
    """仓库相对路径，用于错误信息与校验输出。"""
    return str(path.relative_to(root))


def validate_directory_path(directory_path, source_path: Path, root: Path) -> None:
    """Issue 011：directoryPath 目录段校验。拒绝空/空白/./.. /前后空格/分隔符/
    Unicode Cc 控制字符。

    允许中文、日文、英文、数字、Emoji、中间空格及其他正常 Unicode 字符；
    不同层级允许同名段（如 A/A），不做数组内去重。
    控制字符会破坏 SwiftUI 单行目录显示、对齐和可读性，故按 Unicode category
    Cc 拒绝（覆盖换行、回车、Tab、U+0000～U+001F、U+007F 等）。
    """
    rel = relative_path(source_path, root)
    for segment in directory_path:
        if not isinstance(segment, str):
            raise BuildError(f"{rel}: directoryPath 段必须为字符串: {segment!r}")
        if is_blank(segment) or segment in (".", ".."):
            raise BuildError(f"{rel}: 非法目录段 {segment!r}（不能为空、纯空白、'.' 或 '..'）")
        if segment != segment.strip():
            raise BuildError(f"{rel}: 非法目录段 {segment!r}（不允许前导或尾随空格）")
        if "/" in segment or "\\" in segment:
            raise BuildError(f"{rel}: 非法目录段 {segment!r}（不允许包含 '/' 或 '\\'）")
        if any(unicodedata.category(ch) == "Cc" for ch in segment):
            raise BuildError(f"{rel}: 非法目录段 {segment!r}（不允许 Unicode 控制字符）")


def build_pack(source: dict, source_path: Path) -> dict:
    """source → pack（不含 entryCount，落盘前补全）。"""
    if source.get("schemaVersion") != SCHEMA_VERSION:
        raise BuildError(f"{source_path}: schemaVersion 必须是 {SCHEMA_VERSION}")
    pack_id = source.get("packID")
    if not isinstance(pack_id, str) or not PACK_ID_PATTERN.match(pack_id) or "." not in pack_id or len(pack_id) < 3:
        raise BuildError(f"{source_path}: packID 非法: {pack_id!r}")
    pack_version = source.get("packVersion")
    if not isinstance(pack_version, int) or isinstance(pack_version, bool) or pack_version < 1:
        raise BuildError(f"{source_path}: packVersion 必须是 >= 1 的整数: {pack_version!r}")
    metadata = source.get("metadata")
    validate_metadata(metadata if isinstance(metadata, dict) else {}, pack_id)
    entries = source.get("entries")
    validate_entries(entries, pack_id)

    pack = {
        "schemaVersion": SCHEMA_VERSION,
        "packID": pack_id,
        "packVersion": pack_version,
        "metadata": metadata,
        "entries": entries,
    }
    pack["entryCount"] = len(entries)
    return pack


def optional_metadata_fields(metadata: dict) -> dict:
    """level/description/tags：缺失省略 key；不写 null。"""
    out = {}
    for key in ("level", "description", "tags"):
        if key in metadata and metadata[key] is not None:
            out[key] = metadata[key]
    return out


def catalog_entry(pack: dict, filename: str, pack_bytes: bytes, directory_path: list) -> dict:
    """descriptor：元数据来自 source，大小/哈希/计数来自最终 bytes。

    directoryPath 只存在于 descriptor（Issue 011），pack 正文不含该字段；
    根目录 source 显式写空数组。
    """
    metadata = pack["metadata"]
    entry = {
        "packID": pack["packID"],
        "packVersion": pack["packVersion"],
        "title": metadata["title"],
        "language": metadata["language"],
        "classification": metadata["classification"],
        "entryCount": pack["entryCount"],
        "fileURL": f"packs/{filename}",
        "fileSize": len(pack_bytes),
        "sha256": hashlib.sha256(pack_bytes).hexdigest(),
        "minimumAppVersion": MINIMUM_APP_VERSION,
        "directoryPath": directory_path,
    }
    entry.update(optional_metadata_fields(metadata))
    return entry


def parse_known_version(pack_bytes: bytes, pack_id: str) -> int:
    """读取现有 pack 的 packVersion 用于提升判定；解析失败视为漂移。"""
    try:
        existing = json.loads(pack_bytes)
    except json.JSONDecodeError as e:
        raise BuildError(f"{pack_id}: 现有 pack 文件损坏（手工漂移？）: {e}")
    version = existing.get("packVersion")
    if not isinstance(version, int) or version < 1:
        raise BuildError(f"{pack_id}: 现有 pack 文件 packVersion 非法: {version!r}")
    return version


def compare_pack(existing_bytes: bytes, new_bytes: bytes, pack_id: str, source_version: int) -> None:
    """同 packID 的版本仲裁：内容未变允许；变化必须提升 packVersion。"""
    if existing_bytes == new_bytes:
        return  # 幂等构建：内容未变化，允许成功
    existing_version = parse_known_version(existing_bytes, pack_id)
    if source_version > existing_version:
        return  # 显式提升
    raise BuildError(
        f"{pack_id}: source 内容变化但 packVersion 未提升（现有 {existing_version}，"
        f"source {source_version}）。请提升 source 的 packVersion 后重试。"
    )


def build_all(root: Path) -> dict:
    """返回 {pack_id: {"filename", "bytes", "pack", "directory_path"}}；任何错误立即 fail closed。

    Issue 011：递归扫描 sources/**/*.source.json；directoryPath 由 source 相对
    sources/ 的父目录自动生成，source 文件不得手写或覆盖该字段。写文件前检测
    最终 pack 输出文件名唯一性，冲突 fail closed（不覆盖、不写盘）。
    """
    sources_dir = root / "sources"
    if not sources_dir.is_dir():
        raise BuildError(f"{sources_dir}: 目录不存在")
    built = {}
    filenames = {}
    for source_path in sorted(sources_dir.rglob("*.source.json")):
        source = load_json(source_path)
        if source.get("directoryPath") is not None or (
            isinstance(source.get("metadata"), dict) and "directoryPath" in source["metadata"]
        ):
            raise BuildError(
                f"{relative_path(source_path, root)}: directoryPath 由 sources 目录结构"
                f"自动生成，请删除 source 中手写的 directoryPath。"
            )
        pack = build_pack(source, source_path)
        filename = f"{source_path.stem[:-len('.source')]}.json"
        pack_id = pack["packID"]
        if pack_id in built:
            raise BuildError(f"重复 packID: {pack_id}（{relative_path(source_path, root)}）")
        directory_path = list(source_path.relative_to(sources_dir).parent.parts)
        validate_directory_path(directory_path, source_path, root)
        if filename in filenames:
            raise BuildError(
                f"pack 输出文件名冲突：{filename}\n"
                f"  {relative_path(filenames[filename], root)}\n"
                f"  {relative_path(source_path, root)}\n"
                f"两个 source 的 basename 相同，会生成同一个 pack 文件。"
                f"请修改其中一个 source 的 basename。"
            )
        filenames[filename] = source_path
        built[pack_id] = {
            "filename": filename,
            "bytes": serialize(pack),
            "pack": pack,
            "directory_path": directory_path,
        }
    if not built:
        raise BuildError("sources/ 中没有 *.source.json 文件")
    return built


def read_existing_catalog(root: Path):
    catalog_path = root / "catalog.json"
    if not catalog_path.exists():
        return None
    try:
        with open(catalog_path, encoding="utf-8") as f:
            catalog = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise BuildError(f"catalog.json: 无法解析现有 catalog（手工漂移？）: {e}")
    return catalog


def build_catalog(root: Path, built: dict, now=None) -> dict:
    """构建 catalog 内容；packs 与现有相同则原样复用旧 catalog（byte-identical）。"""
    entries = []
    for pack_id in sorted(built):
        item = built[pack_id]
        entries.append(catalog_entry(item["pack"], item["filename"], item["bytes"], item["directory_path"]))

    existing = read_existing_catalog(root)
    if existing is not None and existing.get("packs") == entries:
        # 内容未变化：原样复用旧 catalog bytes，保证重复构建 byte-identical。
        with open(root / "catalog.json", encoding="utf-8") as f:
            return json.loads(f.read())
    catalog_version = (existing or {}).get("catalogVersion")
    if not isinstance(catalog_version, int) or catalog_version < 1:
        catalog_version = 0
    generated_at = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "catalogVersion": catalog_version + 1,
        "generatedAt": generated_at,
        "packs": entries,
    }


def stale_pack_paths(root: Path, built: dict) -> list[Path]:
    """返回 catalog 明确登记、但已没有对应 source 的旧生成 pack。"""
    existing = read_existing_catalog(root)
    if existing is None:
        return []
    current_filenames = {item["filename"] for item in built.values()}
    stale = []
    for entry in existing.get("packs", []):
        if not isinstance(entry, dict):
            continue
        file_url = entry.get("fileURL")
        if not isinstance(file_url, str) or not file_url.startswith("packs/"):
            continue
        filename = file_url[len("packs/"):]
        # 只接受 catalog 生成器自身的单层 .json 命名；未知文件不在删除范围内。
        if not filename or "/" in filename or not filename.endswith(".json"):
            continue
        if filename in current_filenames:
            continue
        path = root / "packs" / filename
        if path.is_file():
            stale.append(path)
    return sorted(stale)


def write_atomically(root: Path, built: dict, catalog: dict, stale: list[Path]) -> None:
    """临时目录生成 → 校验 → 原子替换；失败清理临时目录。"""
    tmp_dir = Path(tempfile.mkdtemp(prefix=".build-tmp-", dir=root))
    try:
        stale_dir = tmp_dir / "stale"
        stale_dir.mkdir()
        for path in stale:
            os.replace(path, stale_dir / path.name)
        for pack_id, item in built.items():
            (tmp_dir / item["filename"]).write_bytes(item["bytes"])
        catalog_bytes = serialize(catalog)
        (tmp_dir / "catalog.json").write_bytes(catalog_bytes)
        # 替换前再校验一轮最终 bytes（防写入差异）。
        for pack_id, item in built.items():
            if (tmp_dir / item["filename"]).read_bytes() != item["bytes"]:
                raise BuildError(f"{pack_id}: 临时文件写入校验失败")
        for pack_id, item in built.items():
            os.replace(tmp_dir / item["filename"], root / "packs" / item["filename"])
        os.replace(tmp_dir / "catalog.json", root / "catalog.json")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def check_clean(root: Path, built: dict, catalog: dict, stale: list[Path]) -> None:
    """--check：与现有文件逐字节比较，任何差异非零退出。"""
    for pack_id, item in built.items():
        target = root / "packs" / item["filename"]
        if not target.exists():
            raise BuildError(f"{pack_id}: {target} 缺失，需要构建")
        if target.read_bytes() != item["bytes"]:
            raise BuildError(f"{pack_id}: {target} 与重新构建结果不一致（手工漂移？）")
    if stale:
        paths = "\n".join(f"  {path}" for path in stale)
        raise BuildError(f"发现 stale pack（source 已不存在）：\n{paths}")
    catalog_bytes = serialize(catalog)
    target = root / "catalog.json"
    if not target.exists():
        raise BuildError(f"{target}: 缺失，需要构建")
    if target.read_bytes() != catalog_bytes:
        raise BuildError(f"{target}: 与重新构建结果不一致（手工漂移？）")


def summarize(built: dict, catalog: dict) -> None:
    print(f"catalog v{catalog['catalogVersion']}  generatedAt={catalog['generatedAt']}  packs={len(catalog['packs'])}")
    for pack_id in sorted(built):
        item = built[pack_id]
        pack = item["pack"]
        digest = hashlib.sha256(item["bytes"]).hexdigest()
        print(f"  {pack_id:<28} v{pack['packVersion']}  "
              f"{pack['entryCount']:>4} entries  {len(item['bytes']):>6} bytes  sha256={digest[:16]}…")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="构建远程词库 packs 与 catalog")
    parser.add_argument("--check", action="store_true", help="只比较不写盘")
    args = parser.parse_args(argv)

    root = repo_root()
    try:
        built = build_all(root)
        for pack_id, item in built.items():
            existing = root / "packs" / item["filename"]
            if existing.exists():
                compare_pack(existing.read_bytes(), item["bytes"], pack_id, item["pack"]["packVersion"])
        catalog = build_catalog(root, built)
        stale = stale_pack_paths(root, built)
        if args.check:
            check_clean(root, built, catalog, stale)
        else:
            write_atomically(root, built, catalog, stale)
        summarize(built, catalog)
        return 0
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
