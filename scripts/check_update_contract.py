#!/usr/bin/env python3
"""发布端 update contract fixture check（对应 App 侧 issue-071 index-stable 契约）。

验证发布端生成的 pack 满足 App 的 `RemoteWordPackUpdateContract.validateIndexStableUpdate`：

  同一 packID、new.packVersion > old.packVersion、entryCount 不减少、
  且旧范围内逐 index 的 entryID 完全相同 → 合法 update（原位字段修正 + tail append）。
  插入 / 删除 / 重排 → destructive（应使用新 packID 发布）。

fixture 使用 build_catalog.build_pack 真实构建路径；不读取、不修改 production sources。

用法：python3 scripts/check_update_contract.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_catalog import BuildError, build_pack  # noqa: E402

PACK_ID = "com.dai1012.fixture.update.contract"


def make_entry(n: int, meaning: str = "释义") -> dict:
    return {
        "entryID": f"{PACK_ID}-e{n:06d}",
        "term": f"term{n}",
        "reading": f"reading{n}",
        "meaning": f"{meaning}{n}",
    }


def make_source(version: int, entries: list) -> dict:
    return {
        "schemaVersion": 1,
        "packID": PACK_ID,
        "packVersion": version,
        "metadata": {
            "title": "Update Contract Fixture",
            "language": "en",
            "classification": "fixture",
            "level": "test",
            "description": "fixture pack for publisher-side update contract checks",
            "tags": ["fixture"],
        },
        "entries": entries,
    }


def build(version: int, entries: list) -> dict:
    return build_pack(make_source(version, entries), Path(f"<fixture-v{version}>"))


def contract_ok(old: dict, new: dict) -> tuple:
    """镜像 issue-071：返回 (ok, reason)。"""
    if old["packID"] != new["packID"]:
        return False, "packID differs"
    if new["packVersion"] <= old["packVersion"]:
        return False, "packVersion not increased"
    old_e, new_e = old["entries"], new["entries"]
    if len(new_e) < len(old_e):
        return False, f"entryCount decreased ({len(old_e)} -> {len(new_e)})"
    for i, entry in enumerate(old_e):
        if new_e[i]["entryID"] != entry["entryID"]:
            return False, f"entryID changed at index {i}: {entry['entryID']} -> {new_e[i]['entryID']}"
    return True, "index-stable prefix preserved; tail append allowed"


def main() -> int:
    v1 = build(1, [make_entry(1), make_entry(2), make_entry(3)])

    # 1) legal update: in-place correction on index 1 + tail append
    v2_legal = build(2, [make_entry(1), make_entry(2, meaning="修正"), make_entry(3), make_entry(4)])
    ok, reason = contract_ok(v1, v2_legal)
    print(f"CASE legal-in-place+append : {'PASS' if ok else 'FAIL'} — {reason}")
    case1 = ok

    # 2) destructive: reorder (swap index 0/1)
    v2_reorder = build(2, [make_entry(2), make_entry(1), make_entry(3)])
    ok, reason = contract_ok(v1, v2_reorder)
    print(f"CASE destructive-reorder   : {'PASS' if not ok else 'FAIL'} — {reason}")
    case2 = not ok

    # 3) destructive: insert at middle
    v2_insert = build(2, [make_entry(1), make_entry(9), make_entry(2), make_entry(3)])
    ok, reason = contract_ok(v1, v2_insert)
    print(f"CASE destructive-insert    : {'PASS' if not ok else 'FAIL'} — {reason}")
    case3 = not ok

    # 4) destructive: delete
    v2_delete = build(2, [make_entry(1), make_entry(3)])
    ok, reason = contract_ok(v1, v2_delete)
    print(f"CASE destructive-delete    : {'PASS' if not ok else 'FAIL'} — {reason}")
    case4 = not ok

    all_ok = all([case1, case2, case3, case4])
    print(f"UPDATE_CONTRACT: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as error:
        print(f"UPDATE_CONTRACT: FAIL — fixture build error: {error}")
        raise SystemExit(1)
