#!/usr/bin/env python3
"""校验 catalog.json 与 packs/*.json 符合 Issue 005 schema、完整性一致、无漂移。

校验范围（与 JapaneseWordWatch RemoteWordPackValidator 的规则逐条对应，
但这是生成侧独立校验，不是 App Swift validator 的替代品——App 安装时
仍会用 Swift validator 重新校验 raw bytes）：
- JSON 可解析；catalog/pack schema 语义（schemaVersion==1、版本、ID grammar、
  language/classification/level/tags、必填字段、重复检测）
- descriptor↔pack 一致性（packID/packVersion/entryCount/metadata 逐项）
- 完整性（fileSize/SHA-256 基于仓库内原始 pack bytes）
- fileURL 策略（相对路径无 `..`、无 `/` 开头、无反斜杠、percent-encoding
  合法、percent-decode 不产生 `..`；绝对 URL 仅 https；无 http）
- 限制（catalog <= 1 MiB / 100 descriptors；pack <= 10 MiB / 20,000 entries）
- 生成文件无手工漂移：再执行一次 build_catalog.py --check 必须零 diff

用法：python3 scripts/validate_release.py
环境变量：WORDS_REPO_ROOT（同 build_catalog.py）
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_catalog import (  # noqa: E402
    ENTRY_ID_PATTERN,
    LANGUAGE_PATTERN,
    PACK_ID_PATTERN,
    SLUG_PATTERN,
    BuildError,
    load_json,
    repo_root,
)

# App 限制（RemoteWordPackLimits）：catalog 1 MiB / 100 descriptors；
# pack 10 MiB / 20,000 entries。
CATALOG_MAX_BYTES = 1024 * 1024
CATALOG_MAX_DESCRIPTORS = 100
PACK_MAX_BYTES = 10 * 1024 * 1024
PACK_MAX_ENTRIES = 20_000

SCHEMA_VERSION = 1
GENERATED_AT_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,3})?Z$")
VERSION_SEGMENT = re.compile(r"^(?:0|[1-9][0-9]*)$")


class ValidationError(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def days_in_month(year: int, month: int) -> int:
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    return [31, leap and 29 or 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]


def validate_generated_at(value: str) -> None:
    m = GENERATED_AT_PATTERN.match(value)
    check(m, f"generatedAt 非法（须精确 RFC 3339 UTC）: {value!r}")
    year, month, day, hour, minute = (int(g) for g in m.group(1, 2, 3, 4, 5))
    second_text = m.group(6).split(".")[0]
    second = int(second_text)
    check(1 <= month <= 12, f"generatedAt 月份非法: {month}")
    check(1 <= day <= days_in_month(year, month), f"generatedAt 日期非法: {year}-{month}-{day}")
    check(hour <= 23 and minute <= 59 and second <= 59, f"generatedAt 时间非法: {hour}:{minute}:{second}")


def validate_minimum_app_version(value: str) -> None:
    parts = value.split(".")
    check(len(parts) == 3 and all(VERSION_SEGMENT.match(p) for p in parts),
          f"minimumAppVersion 非法（须 MAJOR.MINOR.PATCH 无前导零）: {value!r}")


def validate_pack_id(value: str) -> None:
    check(isinstance(value, str) and 3 <= len(value) <= 128 and "." in value
          and PACK_ID_PATTERN.match(value), f"packID 非法: {value!r}")


def has_valid_percent_encoding(value: str) -> bool:
    return not re.search(r"%(?![0-9a-fA-F]{2})", value)


def is_path_safe_under_all_decoding(path: str) -> bool:
    """近似 App isPathSafeUnderAllDecoding：反复 percent-decode，任何一轮产生
    /、\\ 或最终 segment 为 . / .. 均拒绝。"""
    decoded = path
    for _ in range(8):
        if not has_valid_percent_encoding(decoded):
            return False
        def unescape(s: str) -> tuple:
            out = []
            decoded_any = False
            i = 0
            while i < len(s):
                if s[i] == "%":
                    byte = int(s[i + 1:i + 3], 16)
                    if byte in (0x2F, 0x5C):
                        return None, True  # decode 产生分隔符
                    out.append(chr(byte))
                    decoded_any = True
                    i += 3
                else:
                    out.append(s[i])
                    i += 1
            return "".join(out), decoded_any
        result, did_decode = unescape(decoded)
        if result is None:
            return False
        decoded = result
        if not did_decode:
            return all(seg not in (".", "..") for seg in decoded.split("/"))
    return False


def validate_file_url(value: str, catalog_relative: bool) -> None:
    check(isinstance(value, str) and value != "" and "\\" not in value,
          f"fileURL 非法: {value!r}")
    check(has_valid_percent_encoding(value), f"fileURL percent-encoding 非法: {value!r}")
    scheme_match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value)
    if scheme_match:
        scheme = scheme_match.group(0)[:-1].lower()
        check(scheme == "https", f"fileURL 必须 https，禁止 http/其他: {value!r}")
        check("@" not in value.split("/")[2], f"fileURL 禁止 userinfo: {value!r}")
        check("#" not in value, f"fileURL 禁止 fragment: {value!r}")
    else:
        path_only = value.split("?")[0].split("#")[0]
        check(not path_only.startswith("/") and not path_only.startswith("//"),
              f"fileURL 相对路径禁止 / 开头: {value!r}")
        check(is_path_safe_under_all_decoding(path_only),
              f"fileURL 相对路径含 .. 或异常编码: {value!r}")
        if catalog_relative:
            check(not value.startswith("?"), f"fileURL 禁止 query-only: {value!r}")


def validate_directory_path(value, where: str) -> None:
    """Issue 011：descriptor.directoryPath 必填数组，逐段校验目录名规则。

    允许中文/日文/英文/数字/Emoji/中间空格及其他 Unicode；拒绝空/空白/./..
    /前后空格/分隔符/Unicode Cc 控制字符（与 build_catalog.py 同规则）。
    不同层级允许同名段（如 A/A），不做数组内去重。
    """
    check(isinstance(value, list), f"{where}.directoryPath 必须是数组: {value!r}")
    for index, segment in enumerate(value):
        check(isinstance(segment, str),
              f"{where}.directoryPath[{index}] 必须是字符串: {segment!r}")
        check(segment.strip() != "" and segment not in (".", ".."),
              f"{where}.directoryPath[{index}] 非法: {segment!r}"
              f"（不能为空、纯空白、'.' 或 '..'）")
        check(segment == segment.strip(),
              f"{where}.directoryPath[{index}] 非法: {segment!r}（不允许前导或尾随空格）")
        check("/" not in segment and "\\" not in segment,
              f"{where}.directoryPath[{index}] 非法: {segment!r}（不允许包含 '/' 或 '\\'）")
        check(not any(unicodedata.category(ch) == "Cc" for ch in segment),
              f"{where}.directoryPath[{index}] 非法: {segment!r}（不允许 Unicode 控制字符）")


def validate_tags(tags, where: str) -> None:
    check(isinstance(tags, list), f"{where}.tags 必须是数组")
    seen = set()
    for index, tag in enumerate(tags):
        check(isinstance(tag, str) and SLUG_PATTERN.match(tag) and tag.strip() != "",
              f"{where}.tags[{index}] 非法: {tag!r}")
        check(tag not in seen, f"{where}.tags[{index}] 重复 tag: {tag}")
        seen.add(tag)


def validate_metadata(metadata: dict, where: str) -> None:
    check(isinstance(metadata, dict), f"{where}: metadata 必须是对象")
    title = metadata.get("title")
    check(isinstance(title, str) and title.strip() != "", f"{where}: title 必填且非空白")
    language = metadata.get("language")
    check(isinstance(language, str) and LANGUAGE_PATTERN.match(language), f"{where}: language 非法: {language!r}")
    classification = metadata.get("classification")
    check(isinstance(classification, str) and SLUG_PATTERN.match(classification),
          f"{where}: classification 非法: {classification!r}")
    level = metadata.get("level")
    check(level is None or (isinstance(level, str) and SLUG_PATTERN.match(level)),
          f"{where}: level 非法: {level!r}")
    description = metadata.get("description")
    check(description is None or (isinstance(description, str) and description.strip() != ""),
          f"{where}: description 非法: {description!r}")
    validate_tags(metadata.get("tags", []), where)


def validate_catalog(catalog: dict, catalog_bytes: bytes) -> dict:
    check(len(catalog_bytes) <= CATALOG_MAX_BYTES,
          f"catalog 超出大小限制 {CATALOG_MAX_BYTES} bytes: {len(catalog_bytes)}")
    check(catalog.get("schemaVersion") == SCHEMA_VERSION,
          f"catalog schemaVersion 必须是 {SCHEMA_VERSION}: {catalog.get('schemaVersion')!r}")
    catalog_version = catalog.get("catalogVersion")
    check(isinstance(catalog_version, int) and not isinstance(catalog_version, bool) and catalog_version >= 1,
          f"catalogVersion 必须是 >= 1 的整数: {catalog_version!r}")
    validate_generated_at(catalog.get("generatedAt"))
    packs = catalog.get("packs")
    check(isinstance(packs, list) and len(packs) > 0, "catalog.packs 必须是非空数组")
    check(len(packs) <= CATALOG_MAX_DESCRIPTORS,
          f"catalog descriptors 超出限制 {CATALOG_MAX_DESCRIPTORS}: {len(packs)}")
    seen = set()
    for index, entry in enumerate(packs):
        pack_id = entry.get("packID")
        validate_pack_id(pack_id)
        check(pack_id not in seen, f"catalog.packs[{index}] 重复 packID: {pack_id}")
        seen.add(pack_id)
        pack_version = entry.get("packVersion")
        check(isinstance(pack_version, int) and pack_version >= 1,
              f"catalog.packs[{index}] packVersion 非法: {pack_version!r}")
        title = entry.get("title")
        check(isinstance(title, str) and title.strip() != "", f"catalog.packs[{index}].title 必填")
        language = entry.get("language")
        check(isinstance(language, str) and LANGUAGE_PATTERN.match(language),
              f"catalog.packs[{index}].language 非法: {language!r}")
        classification = entry.get("classification")
        check(isinstance(classification, str) and SLUG_PATTERN.match(classification),
              f"catalog.packs[{index}].classification 非法: {classification!r}")
        level = entry.get("level")
        check(level is None or (isinstance(level, str) and SLUG_PATTERN.match(level)),
              f"catalog.packs[{index}].level 非法: {level!r}")
        entry_count = entry.get("entryCount")
        check(isinstance(entry_count, int) and entry_count >= 1,
              f"catalog.packs[{index}].entryCount 非法: {entry_count!r}")
        validate_file_url(entry.get("fileURL"), catalog_relative=True)
        file_size = entry.get("fileSize")
        check(isinstance(file_size, int) and file_size >= 1,
              f"catalog.packs[{index}].fileSize 非法: {file_size!r}")
        sha256 = entry.get("sha256")
        check(isinstance(sha256, str) and re.fullmatch(r"[0-9a-f]{64}", sha256),
              f"catalog.packs[{index}].sha256 非法: {sha256!r}")
        validate_minimum_app_version(entry.get("minimumAppVersion"))
        validate_directory_path(entry.get("directoryPath"), f"catalog.packs[{index}]")
        description = entry.get("description")
        check(description is None or (isinstance(description, str) and description.strip() != ""),
              f"catalog.packs[{index}].description 非法: {description!r}")
        validate_tags(entry.get("tags", []), f"catalog.packs[{index}]")
    return seen  # 已见 packID 集合


def validate_pack(pack: dict, pack_bytes: bytes, catalog_pack_ids: set) -> str:
    check(len(pack_bytes) <= PACK_MAX_BYTES,
          f"pack 超出大小限制 {PACK_MAX_BYTES} bytes: {len(pack_bytes)}")
    check(pack.get("schemaVersion") == SCHEMA_VERSION,
          f"pack schemaVersion 必须是 {SCHEMA_VERSION}: {pack.get('schemaVersion')!r}")
    check("directoryPath" not in pack,
          "pack 不得包含 directoryPath（Issue 011：该字段只存在于 catalog descriptor）")
    pack_id = pack.get("packID")
    validate_pack_id(pack_id)
    check(pack_id in catalog_pack_ids, f"packID {pack_id!r} 不在 catalog 中")
    pack_version = pack.get("packVersion")
    check(isinstance(pack_version, int) and pack_version >= 1,
          f"{pack_id}: packVersion 非法: {pack_version!r}")
    entry_count = pack.get("entryCount")
    entries = pack.get("entries")
    check(isinstance(entries, list) and len(entries) > 0, f"{pack_id}: entries 必须非空")
    check(len(entries) <= PACK_MAX_ENTRIES,
          f"{pack_id}: entries 超出限制 {PACK_MAX_ENTRIES}: {len(entries)}")
    check(isinstance(entry_count, int) and entry_count >= 1,
          f"{pack_id}: entryCount 非法: {entry_count!r}")
    check(entry_count == len(entries),
          f"{pack_id}: entryCount {entry_count} != entries 实际 {len(entries)}")
    validate_metadata(pack.get("metadata"), pack_id)
    seen = set()
    for index, entry in enumerate(entries):
        check(isinstance(entry, dict), f"{pack_id}: entries[{index}] 必须是对象")
        entry_id = entry.get("entryID")
        check(isinstance(entry_id, str) and ENTRY_ID_PATTERN.match(entry_id),
              f"{pack_id}: entries[{index}].entryID 非法: {entry_id!r}")
        check(entry_id not in seen, f"{pack_id}: 重复 entryID: {entry_id}")
        seen.add(entry_id)
        for key in ("term", "reading", "meaning"):
            value = entry.get(key)
            check(isinstance(value, str), f"{pack_id}: entries[{index}].{key} 缺失或非字符串")
            if value.strip() == "":
                check(key == "reading" and value == "",
                      f"{pack_id}: entries[{index}].{key} 不能为空白")
    return pack_id


def validate_descriptor_consistency(catalog: dict, packs: dict) -> None:
    """descriptor↔pack：packID/version/count/metadata 逐项一致（App integrity 规则）。"""
    by_id = {pack["packID"]: pack for pack in packs.values()}
    for entry in catalog["packs"]:
        pack_id = entry["packID"]
        pack = by_id[pack_id]
        check(pack["packVersion"] == entry["packVersion"],
              f"{pack_id}: packVersion 不一致（pack {pack['packVersion']} vs catalog {entry['packVersion']}）")
        check(pack["entryCount"] == entry["entryCount"],
              f"{pack_id}: entryCount 不一致（pack {pack['entryCount']} vs catalog {entry['entryCount']}）")
        metadata = pack["metadata"]
        for field in ("title", "language", "classification", "level", "description"):
            check(metadata.get(field) == entry.get(field),
                  f"{pack_id}: metadata.{field} 与 catalog 不一致")
        check(metadata.get("tags", []) == entry.get("tags", []),
              f"{pack_id}: metadata.tags 与 catalog 不一致")


def validate_integrity(pack_id: str, pack_bytes: bytes, entry: dict) -> None:
    check(len(pack_bytes) == entry["fileSize"],
          f"{pack_id}: fileSize 不一致（实际 {len(pack_bytes)} vs catalog {entry['fileSize']}）")
    digest = hashlib.sha256(pack_bytes).hexdigest()
    check(digest == entry["sha256"],
          f"{pack_id}: SHA-256 不一致（实际 {digest[:16]}… vs catalog {entry['sha256'][:16]}…）")


def validate_no_drift(root: Path) -> None:
    """生成文件无手工漂移：再执行一次构建必须零 diff。"""
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "build_catalog.py"), "--check"],
        cwd=root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ValidationError(f"build_catalog.py --check 失败（生成文件漂移？）:\n{result.stderr.strip()}")


def main() -> int:
    root = repo_root()
    catalog_path = root / "catalog.json"
    packs_dir = root / "packs"
    try:
        catalog_bytes = catalog_path.read_bytes()
        catalog = load_json(catalog_path)
        catalog_pack_ids = validate_catalog(catalog, catalog_bytes)

        packs = {}
        for entry in catalog["packs"]:
            file_url = entry["fileURL"]
            check(file_url.startswith("packs/") and "/" not in file_url[len("packs/"):],
                  f"{entry['packID']}: fileURL 必须指向仓库内 packs/ 下的直接子文件: {file_url!r}")
            filename = file_url.split("/")[-1]
            path = packs_dir / filename
            check(path.is_file(), f"{entry['packID']}: pack 文件缺失: {path}")
            pack_bytes = path.read_bytes()
            pack = load_json(path)
            pack_id = validate_pack(pack, pack_bytes, catalog_pack_ids)
            packs[pack_id] = pack

        validate_descriptor_consistency(catalog, packs)
        for entry in catalog["packs"]:
            filename = entry["fileURL"].split("/")[-1]
            validate_integrity(entry["packID"], (packs_dir / filename).read_bytes(), entry)
        validate_no_drift(root)

        print(f"VALID: catalog v{catalog['catalogVersion']} packs={len(catalog['packs'])}")
        for entry in catalog["packs"]:
            print(f"  OK {entry['packID']:<28} v{entry['packVersion']} {entry['entryCount']:>4} entries "
                  f"{entry['fileSize']:>6} bytes {entry['fileURL']}")
        return 0
    except (OSError, ValidationError, BuildError) as e:
        print(f"validation error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
