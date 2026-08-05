# Schema 对应关系

本仓库的 `catalog.json` 与 `packs/*.json` 遵循 JapaneseWordWatch Issue 005
「远端词库 JSON v1」schema。权威实现是 App 仓库的 Swift 代码：

- `JapaneseWordiPhone/Services/RemoteWordPacks/RemoteWordPackSchema.swift`
- `JapaneseWordiPhone/Services/RemoteWordPacks/RemoteWordPackValidator.swift`

测试（App 仓库）：

- `JapaneseWordTimelineTests/RemoteWordPackCatalogTests.swift`（schema 语义）
- `JapaneseWordTimelineTests/RemoteWordPackConfigurationTests.swift`（URL 策略）
- Issue 005 tests（`issues/005-remote-word-pack-schema/D.test-plan.md`）

## 文档结构

### catalog.json

```json
{
  "schemaVersion": 1,
  "catalogVersion": 1,
  "generatedAt": "2026-08-05T10:19:49Z",
  "packs": [
    {
      "packID": "com.dai1012.test.basic",
      "packVersion": 1,
      "title": "测试基础词包（Test Basic）",
      "language": "ja",
      "classification": "test",
      "level": "beginner",
      "entryCount": 5,
      "fileURL": "packs/test-basic.json",
      "fileSize": 1243,
      "sha256": "4a5dc0ec…",
      "minimumAppVersion": "1.0.0",
      "description": "…",
      "tags": ["test", "basic"]
    }
  ]
}
```

### packs/<name>.json

```json
{
  "schemaVersion": 1,
  "packID": "com.dai1012.test.basic",
  "packVersion": 1,
  "entryCount": 5,
  "metadata": { "title": "…", "language": "ja", "classification": "test",
                "level": "beginner", "description": "…", "tags": ["test", "basic"] },
  "entries": [
    { "entryID": "test-basic-001", "term": "おはよう",
      "reading": "おはよう", "meaning": "早上好（测试词包）" }
  ]
}
```

## 关键规则（Swift validator 的冻结规则）

| 字段 | 规则 |
| --- | --- |
| `schemaVersion` | 必须是整数 `1`；两阶段 decode，`!= 1` 直接拒绝 |
| `packID` | `^[a-z0-9]+(?:[.-][a-z0-9]+)*$`，3–128 字符，至少一个 `.` |
| `entryID` | `^[a-z0-9][a-z0-9._-]{0,127}$`，作用域内唯一 |
| `packVersion`/`catalogVersion` | `>= 1` 整数 |
| `generatedAt` | 精确 RFC 3339 UTC，真实日历日期 |
| `language` | `^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$` |
| `classification`/`level`/`tag` | 小写 slug `^[a-z0-9]+(?:-[a-z0-9]+)*$` |
| 可选字段（`level`/`description`/`tags`） | 缺失省略 key；**显式 `null` 非法** |
| `fileURL` | 相对路径（无 `/` 开头、无 `..`、percent-encoding 合法）或绝对 https；App 解析相对 URL 到 catalog 目录 |
| `entryCount` | 与 `entries` 实际数量一致 |
| `fileSize`/`sha256` | 与 pack 文件原始字节完全一致（`fileSize`=字节数，`sha256`=小写 64 位 hex） |

## Python 校验与 Swift validator 的关系

`scripts/validate_release.py` 复刻上述规则用于**生成侧**快速校验，但它不是
App Swift validator 的替代品。两者是独立实现，任何 schema 变更必须先在
App 仓库（Issue 005 的 Swift validator 及其测试）落地，再同步到这里。
App 安装 pack 时仍会执行完整的 Swift 校验（structure/semantic/integrity）。

## 发布后验证（真实 Raw URL）

```bash
# 等待 GitHub Raw 缓存更新后：
curl -fsSL https://raw.githubusercontent.com/dai1012/words/main/catalog.json -o /tmp/catalog.json
curl -fsSL https://raw.githubusercontent.com/dai1012/words/main/packs/test-basic.json -o /tmp/test-basic.json
curl -fsSL https://raw.githubusercontent.com/dai1012/words/main/packs/test-travel.json -o /tmp/test-travel.json
shasum -a 256 /tmp/test-basic.json   # 与 catalog.json 中 sha256 一致
cmp /tmp/test-basic.json packs/test-basic.json   # 与本地发布文件 byte-identical
```
